"""Understand an uploaded dataset fast, without calling the model.

The model never sees the whole dataset: it only sees this compact schema
(column names, types, a few example values). That keeps every request small
and is the main reason answers come back in a few seconds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

TIME_HINTS = re.compile(r"(date|month|year|time|day|week|period|mahina|saal|tarikh)", re.I)


@dataclass
class ColumnInfo:
    name: str
    kind: str  # "number" | "time" | "category" | "text"
    examples: list = field(default_factory=list)
    missing: int = 0


@dataclass
class Schema:
    columns: list[ColumnInfo]
    n_rows: int

    def by_name(self) -> dict[str, ColumnInfo]:
        return {c.name: c for c in self.columns}

    def time_col(self) -> str | None:
        for c in self.columns:
            if c.kind == "time":
                return c.name
        return None

    def to_prompt(self) -> str:
        lines = [f"rows: {self.n_rows}"]
        for c in self.columns:
            ex = ", ".join(str(e) for e in c.examples)
            lines.append(f"- {c.name} [{c.kind}] e.g. {ex}")
        return "\n".join(lines)


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Tidy column names and turn numeric-looking text into numbers."""
    df = df.copy()
    df.columns = [re.sub(r"\s+", "_", str(c).strip()).lower() for c in df.columns]
    # make duplicate / blank column names unique (photos and Excel often have them)
    seen: dict[str, int] = {}
    names = []
    for c in df.columns:
        c = c or "col"
        seen[c] = seen.get(c, 0) + 1
        names.append(c if seen[c] == 1 else f"{c}_{seen[c]}")
    df.columns = names
    for col in df.columns:
        s = df[col]
        if not pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_datetime64_any_dtype(s):
            raw = s.where(s.isna(), s.astype(str).str.strip())
            df[col] = raw  # trim stray spaces in text (" Focus", "India ")
            txt = raw.dropna().astype(str)
            # European decimal comma ("48,0", "163,07"): a comma, no dot, and not 3 digits after it
            has_comma = txt.str.fullmatch(r"-?\d*,\d+")
            dec_comma = (len(txt) > 0 and not txt.str.contains(".", regex=False).any()
                         and (has_comma | txt.str.fullmatch(r"-?\d+")).mean() >= 0.9
                         and (has_comma & ~txt.str.fullmatch(r"-?\d{1,3}(,\d{3})+")).any())
            base = raw.astype(str).str.replace(",", "." if dec_comma else "", regex=False)
            cleaned = base.str.replace("₹", "", regex=False).str.strip()
            cleaned = cleaned.replace({"": None, "nan": None, "None": None, "-": None})
            as_num = pd.to_numeric(cleaned, errors="coerce")
            non_null = cleaned.notna().sum()
            if non_null and as_num.notna().sum() / non_null >= 0.9:
                df[col] = as_num
            elif TIME_HINTS.search(col):
                df[col] = _normalise_dates(df[col])
    return df


DAY_FIRST = re.compile(r"^\s*\d{1,2}[/.-]\d{1,2}([/.-]\d{2,4})?\s*$")


def _normalise_dates(s: pd.Series) -> pd.Series:
    """Indian registers write dates day-first (06/10 = 6 October). Turn them into
    sortable ISO dates; values that don't parse are left as they were."""
    txt = s.astype(str).str.strip()
    mask = txt.str.match(DAY_FIRST)
    if mask.mean() < 0.8:
        return s
    year = str(pd.Timestamp.now().year)
    full = txt.where(txt.str.count(r"[/.-]") >= 2, txt + "/" + year).str.replace(r"[.-]", "/", regex=True)
    parsed = pd.to_datetime(full, dayfirst=True, errors="coerce", format="mixed")
    out = parsed.dt.strftime("%Y-%m-%d")
    return out.where(parsed.notna(), s)


def _looks_like_time(name: str, s: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    if TIME_HINTS.search(name) and not pd.api.types.is_float_dtype(s):
        return True
    if s.dtype == object:
        sample = s.dropna().astype(str).head(20)
        if len(sample) and sample.str.match(r"^\d{4}-\d{2}(-\d{2})?$").mean() > 0.8:
            return True
    return False


def build_schema(df: pd.DataFrame) -> Schema:
    cols = []
    for name in df.columns:
        s = df[name]
        missing = int(s.isna().sum())
        if _looks_like_time(name, s):
            kind = "time"
            vals = sorted(s.dropna().astype(str).unique().tolist())
            examples = vals[:2] + (["..."] + vals[-1:] if len(vals) > 3 else vals[2:3])
        elif pd.api.types.is_numeric_dtype(s):
            kind = "number"
            nn = s.dropna()
            if len(nn) and set(nn.unique()) <= {0, 1}:
                examples = ["0/1 yes-no flag", f"{nn.mean() * 100:.0f}% are 1"]
            else:
                examples = [f"min {nn.min():g}", f"max {nn.max():g}", f"mean {nn.mean():.4g}"] if len(nn) else []
        else:
            uniq = s.dropna().astype(str).unique()
            kind = "category" if len(uniq) <= 40 else "text"
            examples = list(uniq[:40]) if kind == "category" else list(uniq[:3])
        cols.append(ColumnInfo(name=name, kind=kind, examples=examples, missing=missing))
    return Schema(columns=cols, n_rows=len(df))
