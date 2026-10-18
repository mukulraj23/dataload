"""Suggested questions for ANY dataset, built from its schema (no AI, instant)."""
from __future__ import annotations

import pandas as pd

from .schema import Schema

ADDITIVE = ("kwh", "unit", "amount", "bill", "total", "sales", "revenue", "cost", "qty", "quantity", "count",
            "waste", "litre", "liter", "kg", "rain", "consumption", "usage", "spend", "expense")


def _pick(names, keys):
    for k in keys:
        for n in names:
            if k in n.lower():
                return n
    return None


def suggestions(schema: Schema, lang: str = "hi", df: pd.DataFrame | None = None) -> list[str]:
    cols = schema.columns
    nums, flags = [], []
    for c in cols:
        if c.kind != "number":
            continue
        if c.examples and str(c.examples[0]).startswith("0/1"):
            flags.append(c.name)
        elif not any(k in c.name.lower() for k in ("id", "s_no", "sno", "serial", "roll")) or len(c.name) > 6:
            nums.append(c.name)
    cats = [c.name for c in cols if c.kind == "category"]
    # prefer small, meaningful groups (2-12 values)
    cats.sort(key=lambda n: (0 if 2 <= len(schema.by_name()[n].examples) <= 12 else 1))
    tcol = schema.time_col()
    additive = _pick(nums, ADDITIVE)
    metric = additive or (nums[1] if len(nums) > 1 else (nums[0] if nums else None))
    agg_hi, agg_en = ("kul", "total") if additive else ("average", "average")

    hi, en = ["Is data ke baare mein batao"], ["Tell me about this data"]
    if flags and cats:
        f, g = flags[-1], cats[0]
        hi.append(f"{g} ke hisaab se kitne % mein {f} hai?")
        en.append(f"What % have {f}, by {g}?")
    if metric and cats:
        hi.append(f"Kis {cats[0]} mein {agg_hi} {metric} sabse zyada hai?")
        en.append(f"Which {cats[0]} has the highest {agg_en} {metric}?")
    if metric and tcol:
        hi.append(f"{metric} ka trend kya hai?")
        en.append(f"What is the trend of {metric}?")
    if cats:
        g = cats[1] if len(cats) > 1 else cats[0]
        hi.append(f"Kitni rows kis {g} mein hain?")
        en.append(f"How many rows are in each {g}?")
    if nums and not tcol:
        n = nums[0]
        hi.append(f"{n} ka distribution kaisa hai?")
        en.append(f"What does the {n} distribution look like?")
    if metric:
        hi.append(f"{agg_hi.capitalize()} {metric} kitna hai?")
        en.append(f"What is the {agg_en} {metric}?")
    out = hi if lang == "hi" else en
    seen, res = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            res.append(q)
    return res[:6]
