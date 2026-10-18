"""Data Health Report: problems in the data, found instantly with pandas (no AI).

Shown before the first question, so the user knows which answers to trust.
"""
from __future__ import annotations

import pandas as pd

from .schema import Schema


def health_report(df: pd.DataFrame, schema: Schema) -> list[dict]:
    """Return a list of issues: {level: 'warn'|'info', hi: str, en: str}."""
    issues: list[dict] = []

    dup = int(df.duplicated().sum())
    if dup:
        issues.append({"level": "warn", "hi": f"{dup} duplicate row(s) mili: inhe 2 baar gina ja sakta hai.",
                       "en": f"{dup} duplicate row(s) found: they may be double counted."})

    for c in schema.columns:
        if c.missing:
            pct = c.missing / max(len(df), 1) * 100
            issues.append({"level": "warn" if pct > 5 else "info",
                           "hi": f"'{c.name}' mein {c.missing} value khaali hai ({pct:.0f}%).",
                           "en": f"'{c.name}' has {c.missing} empty value(s) ({pct:.0f}%)."})

    # Missing time periods per group (e.g. a building with no March record)
    tcol = schema.time_col()
    cats = [c.name for c in schema.columns if c.kind == "category"]
    if tcol and cats:
        g = cats[0]
        periods = set(df[tcol].dropna().astype(str))
        groups = list(df.groupby(g))
        cover = [sub[tcol].nunique() / max(len(periods), 1) for _, sub in groups]
        # only meaningful when every group is meant to report every period (e.g. monthly
        # bills per building); skip for rotating/daily logs where gaps are normal
        regular = len(periods) <= 60 and cover and sorted(cover)[len(cover) // 2] >= 0.75
        for key, sub in (groups if regular else []):
            gaps = sorted(periods - set(sub[tcol].dropna().astype(str)))
            if gaps:
                issues.append({"level": "warn",
                               "hi": f"'{key}' ka data in period(s) mein nahi hai: {', '.join(gaps[:4])}.",
                               "en": f"'{key}' has no record for: {', '.join(gaps[:4])}."})

    # Unusual values (robust z-score). Inside each group only for "entity over time" data
    # (a hostel using 2x its normal power is odd even if the number looks normal campus-wide).
    label = cats[0] if (cats and tcol) else None
    odd_items = []
    for c in schema.columns:
        s = df[c.name]
        if c.kind != "number" or s.nunique() <= 10:   # skip ids-like codes, 0/1 flags, ratings
            continue
        nonzero = s[s != 0].dropna()
        zeros = int((s == 0).sum())
        if zeros and len(nonzero) and nonzero.min() > 0.25 * nonzero.median():
            pct = zeros / len(df) * 100
            issues.append({"level": "warn",
                           "hi": f"'{c.name}' mein {zeros} jagah 0 hai ({pct:.0f}%): shayad ye khaali/missing value hai.",
                           "en": f"'{c.name}' is 0 in {zeros} rows ({pct:.0f}%): probably missing values."})
            s = s.where(s != 0)
        odd_idx = []
        groups = list(df.assign(**{c.name: s}).groupby(label)) if label else [(None, df.assign(**{c.name: s}))]
        if not any(len(sub[c.name].dropna()) >= 5 for _, sub in groups):
            groups = [(None, df.assign(**{c.name: s}))]
        for _, sub in groups:
            v = sub[c.name].dropna()
            if len(v) < 5:
                continue
            med = v.median()
            mad = (v - med).abs().median()
            if not mad:
                continue
            z = 0.6745 * (v - med) / mad
            odd_idx += list(z[z.abs() > 4].index)
        if odd_idx:
            odd = df.loc[odd_idx]
            def where(i, r):
                if label:
                    return f"{r[label]} {r[tcol]}".strip()
                return f"row {i + 1}"
            ex = ", ".join(f"{where(i, r)} ({r[c.name]:,.0f})" for i, r in odd.head(3).iterrows())
            odd_items.append((len(odd), {"level": "warn",
                               "hi": f"'{c.name}' mein {len(odd)} ajeeb value(s): {ex}. Check kar lo.",
                               "en": f"'{c.name}' has {len(odd)} unusual value(s): {ex}. Worth checking."}))
        if (df[c.name] < 0).any() and (df[c.name] < 0).mean() < 0.2:
            issues.append({"level": "info", "hi": f"'{c.name}' mein kuch negative values hain.",
                           "en": f"'{c.name}' has some negative values."})
    issues += [it for _, it in sorted(odd_items, key=lambda x: -x[0])[:4]]

    if not issues:
        issues.append({"level": "info", "hi": "Data saaf dikh raha hai. Koi badi problem nahi mili.",
                       "en": "Data looks clean. No major problems found."})
    return issues
