"""Turn Gemma's JSON plan into real pandas code, run it, and explain the result.

Every number the user sees comes from this code, never from the model.
The exact code that ran is shown in the app as proof.
"""
from __future__ import annotations

import numbers
from dataclasses import dataclass, field

import re

import pandas as pd
import plotly.express as px

from . import extra
from .schema import Schema

AGGS = {"sum", "mean", "max", "min", "median", "count"}
AGG_HI = {"sum": "kul", "mean": "average", "max": "sabse zyada", "min": "sabse kam", "median": "median", "count": "ginti"}
OPS = {"==", "!=", ">", "<", ">=", "<=", "in", "contains"}


class PlanError(Exception):
    def __init__(self, hi: str, en: str):
        super().__init__(en)
        self.hi, self.en = hi, en


@dataclass
class Answer:
    ok: bool
    hi: str
    en: str
    code: str = ""
    table: pd.DataFrame | None = None
    rows_used: pd.DataFrame | None = None
    chart: object | None = None
    caveats: list[dict] = field(default_factory=list)
    confidence: str = "high"  # high | medium | low


def fmt(x) -> str:
    if isinstance(x, numbers.Number) and not pd.isna(x):
        if float(x).is_integer() or abs(x) >= 100:
            return f"{x:,.0f}"
        return f"{x:,.2f}"
    return str(x)


def _match_value(df: pd.DataFrame, col: str, value):
    """Case-insensitive match so 'boys hostel b' finds 'Boys Hostel B'."""
    if isinstance(value, list):
        return [_match_value(df, col, v) for v in value]
    if pd.api.types.is_numeric_dtype(df[col]):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    uniq = df[col].dropna().astype(str).unique()
    v = str(value).strip().lower()
    for u in uniq:
        if u.lower() == v:
            return u
    hits = [u for u in uniq if v in u.lower()]
    return hits[0] if len(hits) == 1 else value


def _check_col(schema: Schema, col, role: str):
    if col is None:
        raise PlanError(f"Sawal ke liye '{role}' column chahiye, jo samajh nahi aaya.",
                        f"Could not work out which column to use as {role}.")
    if col not in schema.by_name():
        raise PlanError(f"Data mein '{col}' naam ka column nahi hai, isliye ye jawab nahi de sakte.",
                        f"The data has no column called '{col}', so this can't be answered.")
    return col


def build_code(plan: dict, df: pd.DataFrame, schema: Schema) -> tuple[str, dict]:
    """Return (python code, meta). Code uses `df` and leaves `rows` and `result`."""
    intent = plan.get("intent", "unsupported")
    if intent == "unsupported":
        msg = plan.get("missing") or "is sawal ke liye zaroori data"
        raise PlanError(f"Ye jawab is data se nahi nikal sakta. Kami: {msg}.",
                        f"This data can't answer that. Missing: {msg}.")

    agg = plan.get("agg") or ("count" if intent == "count" else "sum")
    if agg not in AGGS:
        agg = "sum"
    lines = ["rows = df"]
    meta = {"intent": intent, "agg": agg}

    for f in plan.get("filters") or []:
        col = _check_col(schema, f.get("col"), "filter")
        op = f.get("op", "==")
        if op not in OPS:
            op = "=="
        val = _match_value(df, col, f.get("value"))
        if op == "in":
            lines.append(f"rows = rows[rows[{col!r}].isin({list(val) if isinstance(val, list) else [val]!r})]")
        elif op == "contains":
            lines.append(f"rows = rows[rows[{col!r}].astype(str).str.contains({str(val)!r}, case=False, na=False)]")
        else:
            lines.append(f"rows = rows[rows[{col!r}] {op} {val!r}]")

    metric = None
    if intent != "count":
        metric = _check_col(schema, plan.get("metric"), "metric")
        if agg != "count" and schema.by_name()[metric].kind != "number":
            raise PlanError(f"'{metric}' number wala column nahi hai, uska {AGG_HI[agg]} nahi nikal sakte.",
                            f"'{metric}' is not a numeric column.")
    meta["metric"] = metric

    if intent == "count":
        lines.append("result = len(rows)")

    elif intent == "aggregate":
        lines.append(f"result = rows[{metric!r}].{agg}()")

    elif intent == "rank":
        g = _check_col(schema, plan.get("group_by"), "group_by")
        asc = plan.get("order") == "asc"
        n = int(plan.get("top_n") or 10)
        lines.append(f"result = rows.groupby({g!r})[{metric!r}].{agg}().sort_values(ascending={asc}).head({n})")
        meta.update(group_by=g, order="asc" if asc else "desc")

    elif intent == "trend":
        t = _check_col(schema, plan.get("group_by") if plan.get("group_by") == schema.time_col() else schema.time_col(),
                       "time")
        lines.append(f"result = rows.groupby({t!r})[{metric!r}].{agg}().sort_index()")
        meta.update(group_by=t)

    elif intent == "compare":
        cmp_ = plan.get("compare") or {}
        c = _check_col(schema, cmp_.get("col"), "compare")
        a, b = _match_value(df, c, cmp_.get("a")), _match_value(df, c, cmp_.get("b"))
        g = plan.get("group_by")
        if g:
            _check_col(schema, g, "group_by")
            lines.append(f"pv = rows[rows[{c!r}].isin([{a!r}, {b!r}])].pivot_table(index={g!r}, columns={c!r}, "
                         f"values={metric!r}, aggfunc={agg!r})")
            lines.append(f"pv['change'] = pv[{b!r}] - pv[{a!r}]")
            lines.append(f"pv['change_%'] = (pv['change'] / pv[{a!r}] * 100).round(1)")
            lines.append("result = pv.sort_values('change', ascending=False)")
        else:
            lines.append(f"va = rows.loc[rows[{c!r}] == {a!r}, {metric!r}].{agg}()")
            lines.append(f"vb = rows.loc[rows[{c!r}] == {b!r}, {metric!r}].{agg}()")
            lines.append("result = {'a': va, 'b': vb, 'change': vb - va, "
                         "'change_%': round((vb - va) / va * 100, 1) if va else None}")
        lines.append(f"rows = rows[rows[{c!r}].isin([{a!r}, {b!r}])]")
        meta.update(compare_col=c, a=a, b=b, group_by=g)

    elif intent == "ratio":
        den = _check_col(schema, plan.get("denominator"), "denominator")
        g = plan.get("group_by")
        meta.update(denominator=den, group_by=g)
        lines.append(f"rows = rows[rows[{den!r}].notna() & (rows[{den!r}] != 0)]")
        if g:
            _check_col(schema, g, "group_by")
            lines.append(f"s = rows.groupby({g!r})[[{metric!r}, {den!r}]].{'sum' if agg == 'sum' else 'mean'}()")
            lines.append(f"result = (s[{metric!r}] / s[{den!r}]).round(2).sort_values(ascending=False)")
        else:
            lines.append(f"result = round(rows[{metric!r}].sum() / rows[{den!r}].sum(), 2)")
    else:
        raise PlanError("Sawal ka type samajh nahi aaya.", "Could not understand the question type.")

    return "\n".join(lines), meta


def _filtered(plan, df, schema):
    """Apply only the plan's filters (used by distribution)."""
    lines = ["rows = df"]
    for f in plan.get("filters") or []:
        col = _check_col(schema, f.get("col"), "filter")
        op = f.get("op", "==") if f.get("op") in OPS else "=="
        val = _match_value(df, col, f.get("value"))
        if op == "in":
            lines.append(f"rows = rows[rows[{col!r}].isin({list(val) if isinstance(val, list) else [val]!r})]")
        elif op == "contains":
            lines.append(f"rows = rows[rows[{col!r}].astype(str).str.contains({str(val)!r}, case=False, na=False)]")
        else:
            lines.append(f"rows = rows[rows[{col!r}] {op} {val!r}]")
    ns = {"df": df}
    exec("\n".join(lines), {"__builtins__": {"list": list}}, ns)  # noqa: S102 - code built by us
    return ns["rows"], lines


def run_special(plan: dict, df: pd.DataFrame, schema: Schema) -> Answer | None:
    intent = plan.get("intent")
    try:
        if intent == "overview":
            hi, en, table, chart, code = extra.overview(df, schema)
            return Answer(ok=True, hi=hi, en=en, table=table, chart=chart, code=code, rows_used=df,
                          confidence="high")
        if intent == "distribution":
            col = _check_col(schema, plan.get("group_by") or plan.get("metric"), "column")
            rows, lines = _filtered(plan, df, schema)
            if rows.empty:
                return Answer(ok=False, hi="Filter ke baad koi row nahi bachi.", en="No rows matched.", confidence="low")
            hi, en, table, chart, code = extra.distribution(df, schema, col, rows)
            return Answer(ok=True, hi=hi, en=en, table=table, chart=chart, code="\n".join(lines + [code]),
                          rows_used=rows, confidence="high" if len(rows) >= 10 else "medium")
        if intent == "pandas":
            code = str(plan.get("code") or "").strip()
            label_hi = str(plan.get("label_hi") or plan.get("label") or "Jawab")[:120]
            label_en = str(plan.get("label_en") or plan.get("label") or "Answer")[:120]
            try:
                result = extra.run_pandas(code, df)
            except extra.SafetyError as e:
                return Answer(ok=False, hi=f"Ye calculation safe nahi lagi, isliye nahi chalayi ({e}).",
                              en=f"That calculation was blocked for safety ({e}).", code=code, confidence="low")
            except Exception as e:
                return Answer(ok=False, hi="Is sawal ka calculation fail ho gaya. Thoda alag tareeke se poocho.",
                              en=f"The calculation failed ({type(e).__name__}). Try rephrasing.", code=code,
                              confidence="low")
            hi, en, table, chart, ok = extra.describe_result(result, label_hi, label_en)
            cav = [{"hi": "Ye calculation Gemma ne likha aur pandas ne chalaya. Code 'Proof' mein check kar lo.",
                    "en": "Gemma wrote this calculation and pandas ran it. Check the code under Proof."}]
            return Answer(ok=ok, hi=hi, en=en, table=table, chart=chart, code=code, rows_used=df,
                          caveats=cav, confidence="medium")
    except PlanError as e:
        return Answer(ok=False, hi=e.hi, en=e.en, confidence="low")
    return None


def run(plan: dict, df: pd.DataFrame, schema: Schema) -> Answer:
    special = run_special(plan, df, schema)
    if special is not None:
        if special.chart is not None:
            special.chart.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=360)
        return special
    try:
        code, meta = build_code(plan, df, schema)
    except PlanError as e:
        return Answer(ok=False, hi=e.hi, en=e.en, confidence="low")

    ns = {"df": df, "pd": pd}
    try:
        exec(code, {"__builtins__": {"round": round, "len": len, "list": list}}, ns)  # noqa: S102 - code built by us
    except Exception as e:  # pragma: no cover
        return Answer(ok=False, hi=f"Calculation mein dikkat aayi: {e}", en=f"Calculation failed: {e}", code=code,
                      confidence="low")

    result, rows = ns["result"], ns["rows"]
    ans = explain(result, rows, meta, df, schema, plan)
    ans.code = code
    ans.rows_used = rows
    return ans


NICE = {
    "kwh": ("bijli (kWh)", "electricity (kWh)"), "units": ("units", "units"),
    "bill_rs": ("bill (₹)", "bill (₹)"), "bill": ("bill", "bill"), "amount": ("amount", "amount"),
    "students": ("students", "students"), "rate_per_kwh": ("rate per kWh", "rate per kWh"),
    "rows": ("rows", "rows"),
}
SINGULAR = {"students": "student", "rooms": "room", "people": "person", "users": "user", "households": "household"}


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def per(v) -> str:
    """'2026-08' -> 'Aug 2026', '2026-10-06' -> '6 Oct 2026'; anything else unchanged."""
    t = str(v)
    m = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$", t)
    if not m or not 1 <= int(m.group(2)) <= 12:
        return t
    mon = MONTHS[int(m.group(2)) - 1]
    return f"{int(m.group(3))} {mon} {m.group(1)}" if m.group(3) else f"{mon} {m.group(1)}"


def nice(col: str, lang: str, singular: bool = False) -> str:
    """Readable name for a column in answers: 'bill_rs' -> 'bill (₹)'."""
    if not col:
        return ""
    if singular and col in SINGULAR:
        return SINGULAR[col]
    if col in NICE:
        return NICE[col][0 if lang == "hi" else 1]
    return col.replace("_", " ")


def explain(result, rows, meta, df, schema, plan) -> Answer:
    intent, agg, metric = meta["intent"], meta["agg"], meta.get("metric")
    caveats: list[dict] = []
    table, chart = None, None
    m = metric or "rows"
    mh, me = nice(m, "hi"), nice(m, "en")
    den_col = meta.get("denominator") or ""
    dh, de = nice(den_col, "hi", singular=True), nice(den_col, "en", singular=True)

    if len(rows) == 0:
        return Answer(ok=False, hi="Filter ke baad koi row nahi bachi. Naam/value check karo.",
                      en="No rows matched. Check the names or values used.", confidence="low")

    if agg in ("mean", "median", "max", "min") and intent in ("rank", "trend", "compare"):
        mh, me = f"{AGG_HI[agg]} {mh}", f"{ {'mean': 'average', 'median': 'median', 'max': 'max', 'min': 'min'}[agg]} {me}"
    if metric and metric in rows and pd.api.types.is_numeric_dtype(rows[metric]):
        z = int((rows[metric] == 0).sum())
        nz = rows.loc[rows[metric] != 0, metric].dropna()
        if z and len(nz) and nz.min() > 0.25 * nz.median() and rows[metric].nunique() > 10:
            caveats.append({"hi": f"'{metric}' mein {z} jagah 0 hai (shayad missing). Ye {AGG_HI[agg]} ko bigaad sakta hai.",
                            "en": f"'{metric}' is 0 in {z} rows (probably missing); this can distort the {agg}."})
    if intent == "count":
        hi = f"{len(rows):,} rows is sharat se match karti hain (kul {len(df):,} mein se)."
        en = f"{len(rows):,} rows match (out of {len(df):,})."
    elif intent == "aggregate":
        word_en = {"sum": "Total", "mean": "Average", "max": "Maximum", "min": "Minimum", "median": "Median",
                   "count": "Count of"}[agg]
        hi = f"{AGG_HI[agg].capitalize()} {mh} {fmt(result)} hai ({len(rows):,} rows se)."
        en = f"{word_en} {me} is {fmt(result)} (from {len(rows):,} rows)."

    elif intent == "rank":
        s = result.dropna()
        if s.empty:
            return Answer(ok=False, hi="Ranking ke liye data nahi mila.", en="No data to rank.", confidence="low")
        top, val = s.index[0], s.iloc[0]
        word_hi = "sabse kam" if meta["order"] == "asc" else "sabse zyada"
        word_en = "lowest" if meta["order"] == "asc" else "highest"
        hi = f"{top} mein {mh} {word_hi} hai: {fmt(val)}."
        en = f"{top} has the {word_en} {me}: {fmt(val)}."
        if len(s) > 1:
            gap = abs(val - s.iloc[1])
            hi += f" Dusre number ({s.index[1]}) se {fmt(gap)} ka fark."
            en += f" That's {fmt(gap)} more than #2 ({s.index[1]})." if meta["order"] == "desc" else ""
        table = s.reset_index()
        chart = px.bar(table, x=meta["group_by"], y=m, text_auto=".3s")
        tcol_r = schema.time_col()
        if tcol_r and agg in ("sum", "count") and meta["group_by"] != tcol_r:
            n_per = rows.groupby(meta["group_by"])[tcol_r].nunique()
            full = n_per.max()
            short = n_per[n_per < full]
            if len(short):
                names = ", ".join(map(str, short.index[:3]))
                caveats.append({"hi": f"{names} ka kuch periods ka data nahi hai, isliye unka total kam dikh sakta hai.",
                                "en": f"{names} is missing some periods, so its total may look lower than it really is."})

    elif intent == "trend":
        s = result.dropna()
        if len(s) < 2:
            return Answer(ok=False, hi="Trend ke liye kam se kam 2 period chahiye.",
                          en="Need at least 2 periods for a trend.", confidence="low")
        first, last = s.iloc[0], s.iloc[-1]
        ch = (last - first) / first * 100 if first else 0
        peak = s.idxmax()
        dir_hi = "badha" if ch > 0 else "ghata"
        dir_en = "rose" if ch > 0 else "fell"
        hi = f"{per(s.index[0])} se {per(s.index[-1])} tak {mh} {abs(ch):.1f}% {dir_hi}. Sabse zyada {per(peak)} mein ({fmt(s.max())})."
        en = f"From {per(s.index[0])} to {per(s.index[-1])}, {me} {dir_en} {abs(ch):.1f}%. Peak was {per(peak)} ({fmt(s.max())})."
        table = s.reset_index()
        chart = px.line(table, x=meta["group_by"], y=m, markers=True)

    elif intent == "compare":
        a, b = meta["a"], meta["b"]
        if isinstance(result, dict):
            pct = result["change_%"]
            dir_hi = "zyada" if result["change"] > 0 else "kam"
            hi = f"{per(b)} mein {mh} {fmt(result['b'])} hai, {per(a)} ({fmt(result['a'])}) se {fmt(abs(result['change']))} {dir_hi}"
            hi += f" ({pct:+}%)." if pct is not None else "."
            en = f"{me[:1].upper() + me[1:]} was {fmt(result['a'])} in {per(a)} and {fmt(result['b'])} in {per(b)}"
            en += f" ({pct:+}%)." if pct is not None else "."
            table = pd.DataFrame({"period": [a, b], m: [result["a"], result["b"]]})
            chart = px.bar(table, x="period", y=m, text_auto=".3s")
        else:
            r = result.dropna(subset=["change"])
            top = r.index[0]
            hi = f"{per(a)} se {per(b)} ke beech sabse zyada badhat {top} mein: {fmt(r.loc[top, 'change'])} ({r.loc[top, 'change_%']:+}%)."
            en = f"Biggest increase from {per(a)} to {per(b)}: {top}, {fmt(r.loc[top, 'change'])} ({r.loc[top, 'change_%']:+}%)."
            table = result.reset_index()
            long = table.melt(id_vars=meta["group_by"], value_vars=[a, b], var_name=meta["compare_col"], value_name=m)
            chart = px.bar(long, x=meta["group_by"], y=m, color=meta["compare_col"], barmode="group")
            if result[[a, b]].isna().any().any():
                caveats.append({"hi": "Kuch groups ka ek period ka data nahi hai, unka change nahi nikla.",
                                "en": "Some groups are missing one period, so their change is blank."})

    elif intent == "ratio":
        den = meta["denominator"]
        dropped = int(df[den].isna().sum() + (df[den] == 0).sum())
        if isinstance(result, pd.Series):
            top = result.index[0]
            hi = f"Per {dh} {mh} sabse zyada {top} mein: {fmt(result.iloc[0])}."
            en = f"Highest {me} per {de}: {top} at {fmt(result.iloc[0])}."
            table = result.rename(f"{m}_per_{den}").reset_index()
            chart = px.bar(table, x=meta["group_by"], y=f"{m}_per_{den}", text_auto=".3s")
        else:
            hi = f"Per {dh} {mh}: {fmt(result)}."
            en = f"{me} per {de}: {fmt(result)}."
        if dropped:
            missing_groups = []
            g = meta.get("group_by")
            if g:
                missing_groups = sorted(df.loc[df[den].isna() | (df[den] == 0), g].astype(str).unique())[:5]
            caveats.append({"hi": f"{dropped} rows mein '{den}' khaali hai, unhe chhoda gaya"
                                  + (f" ({', '.join(missing_groups)} ka ratio nahi nikal sakta)." if missing_groups else "."),
                            "en": f"{dropped} rows have no '{den}' and were left out"
                                  + (f" (no ratio possible for {', '.join(missing_groups)})." if missing_groups else ".")})
    else:
        hi = en = str(result)

    # Confidence: based on how much data the answer rests on and gaps found
    conf = "high"
    if len(rows) < 3:
        conf = "low"
        caveats.append({"hi": "Sirf kuch hi rows par based hai, pakka nateeja mat maano.",
                        "en": "Based on very few rows; don't treat it as conclusive."})
    elif caveats:
        conf = "medium"
    tcol = schema.time_col()
    if tcol and intent in ("trend", "rank", "aggregate") and metric:
        nulls = int(rows[metric].isna().sum())
        if nulls:
            conf = "medium"
            caveats.append({"hi": f"In rows mein {nulls} jagah {mh} khaali hai.",
                            "en": f"{nulls} empty {me} values in these rows."})

    if chart is not None:
        chart.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=360)
    return Answer(ok=True, hi=hi, en=en, table=table, chart=chart, caveats=caveats, confidence=conf)
