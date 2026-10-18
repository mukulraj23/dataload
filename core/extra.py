"""Answers beyond the fixed templates.

- overview:      "Data ke baare mein batao" -> summary of every column (no AI numbers)
- distribution:  "Kitne log kis chest pain type mein?" -> counts / histogram
- pandas:        any other question -> Gemma writes ONE short pandas snippet, we check it
                 (no imports, no files, no dunder tricks), run it on a copy of the data,
                 and show the code as proof. Numbers still come from pandas, not the model.
"""
from __future__ import annotations

import ast
import numbers

import numpy as np
import pandas as pd
import plotly.express as px

from .schema import Schema


class SafetyError(Exception):
    pass


def _fmt(x) -> str:
    if isinstance(x, (bool, np.bool_)):
        return "Haan / Yes" if x else "Nahi / No"
    if isinstance(x, numbers.Number) and not pd.isna(x):
        x = float(x)
        if x.is_integer() or abs(x) >= 100:
            return f"{x:,.0f}"
        return f"{x:,.2f}".rstrip("0").rstrip(".")
    return str(x)


def _is_binary(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) and set(s.dropna().unique()) <= {0, 1}


# ---------------------------------------------------------------- overview
def overview(df: pd.DataFrame, schema: Schema):
    nums, cats, flags = [], [], []
    rows = []
    for c in schema.columns:
        s = df[c.name]
        filled = int(s.notna().sum())
        if c.kind == "number" and _is_binary(s):
            pct = s.mean() * 100
            flags.append(f"{c.name} {pct:.0f}%")
            rows.append([c.name, "yes/no (0/1)", f"{pct:.1f}% = 1", filled])
        elif c.kind == "number":
            nums.append(f"{c.name} {_fmt(s.min())}-{_fmt(s.max())} (avg {_fmt(s.mean())})")
            rows.append([c.name, "number", f"{_fmt(s.min())} to {_fmt(s.max())}, avg {_fmt(s.mean())}", filled])
        elif c.kind == "time":
            v = sorted(s.dropna().astype(str).unique())
            rows.append([c.name, "time", f"{v[0]} to {v[-1]} ({len(v)} periods)" if v else "", filled])
        else:
            vc = s.astype(str).value_counts()
            top = ", ".join(f"{k} {v}" for k, v in vc.head(3).items())
            cats.append(f"{c.name} ({top})")
            rows.append([c.name, "category" if c.kind == "category" else "text", f"{len(vc)} values: {top}", filled])
    table = pd.DataFrame(rows, columns=["column", "type", "summary", "filled"])
    hi = f"Is data mein {len(df):,} rows aur {len(df.columns)} columns hain."
    en = f"This data has {len(df):,} rows and {len(df.columns)} columns."
    if nums:
        hi += " Numbers: " + "; ".join(nums[:3]) + "."
        en += " Numbers: " + "; ".join(nums[:3]) + "."
    if cats:
        hi += " Groups: " + "; ".join(cats[:2]) + "."
        en += " Groups: " + "; ".join(cats[:2]) + "."
    if flags:
        hi += " Yes/No columns: " + ", ".join(flags[:3]) + "."
        en += " Yes/No columns: " + ", ".join(flags[:3]) + "."
    code = ("summary = []\nfor col in df.columns:\n    s = df[col]\n"
            "    summary.append((col, s.dtype, s.min() if s.dtype != object else s.value_counts().head(3), s.notna().sum()))\n"
            "result = summary")
    return hi, en, table, None, code


# ---------------------------------------------------------------- distribution
def distribution(df: pd.DataFrame, schema: Schema, col: str, rows: pd.DataFrame):
    s = rows[col]
    kind = schema.by_name()[col].kind
    if kind == "number" and s.nunique() > 12:
        bins = pd.cut(s.dropna(), bins=8)
        vc = bins.value_counts().sort_index()
        table = pd.DataFrame({col: [f"{iv.left:,.0f}-{iv.right:,.0f}" for iv in vc.index], "count": vc.values})
        top = table.iloc[int(np.argmax(table["count"]))]
        hi = f"{col} zyada tar {top[col]} ke beech hai ({top['count']} rows). Average {_fmt(s.mean())}, median {_fmt(s.median())}."
        en = f"Most {col} values fall in {top[col]} ({top['count']} rows). Average {_fmt(s.mean())}, median {_fmt(s.median())}."
        code = f"result = pd.cut(rows[{col!r}], bins=8).value_counts().sort_index()"
    else:
        vc = s.astype(str).value_counts()
        table = pd.DataFrame({col: vc.index, "count": vc.values})
        total = int(vc.sum())
        k, v = vc.index[0], int(vc.iloc[0])
        hi = f"Sabse zyada '{k}' hai: {v:,} rows ({v / total * 100:.0f}%), kul {len(vc)} alag values."
        en = f"Most common is '{k}': {v:,} rows ({v / total * 100:.0f}%), out of {len(vc)} distinct values."
        code = f"result = rows[{col!r}].value_counts()"
    chart = px.bar(table.head(30), x=col, y="count")
    return hi, en, table, chart, code


# ---------------------------------------------------------------- safe pandas
BANNED_NAMES = {"open", "eval", "exec", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr",
                "delattr", "input", "breakpoint", "help", "exit", "quit", "memoryview", "type", "object", "super",
                "os", "sys", "subprocess", "shutil", "pathlib", "importlib", "builtins", "dir"}
BANNED_ATTR_PREFIX = ("to_", "read_", "_")
ALLOWED_TO = {"to_frame", "to_list", "to_dict", "to_numpy", "to_period", "to_timestamp", "to_datetime", "to_numeric"}
SAFE_BUILTINS = {k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k)
                 for k in ("len", "round", "min", "max", "sum", "abs", "sorted", "list", "dict", "range", "zip",
                           "float", "int", "str", "bool", "enumerate", "set", "tuple", "any", "all")}


def check_code(code: str) -> ast.Module:
    if len(code) > 1500:
        raise SafetyError("code too long")
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.While, ast.Global, ast.Nonlocal, ast.With,
                             ast.AsyncFunctionDef, ast.FunctionDef, ast.ClassDef, ast.Try, ast.Delete)):
            raise SafetyError(f"{type(node).__name__} not allowed")
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            raise SafetyError(f"name {node.id} not allowed")
        if isinstance(node, ast.Attribute):
            a = node.attr
            if a.startswith("__") or (a.startswith(BANNED_ATTR_PREFIX) and a not in ALLOWED_TO):
                raise SafetyError(f"attribute {a} not allowed")
            if a in {"eval", "query", "pipe"}:
                raise SafetyError(f"attribute {a} not allowed")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            raise SafetyError("dunder string not allowed")
    if not any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "result" for t in n.targets)
               for n in tree.body):
        raise SafetyError("code must assign result")
    return tree


def run_pandas(code: str, df: pd.DataFrame):
    check_code(code)
    ns = {"df": df.copy(), "pd": pd, "np": np}
    exec(compile(code, "<gemma>", "exec"), {"__builtins__": SAFE_BUILTINS}, ns)  # noqa: S102 - AST checked above
    return ns["result"]


def describe_result(result, label_hi: str, label_en: str):
    """Turn whatever the snippet returned into a sentence, a table and maybe a chart."""
    table, chart = None, None
    if isinstance(result, pd.DataFrame) and result.shape[1] == 1:
        result = result.iloc[:, 0]
    if isinstance(result, (np.generic,)):
        result = result.item()
    if isinstance(result, pd.Series):
        s = result.dropna()
        if s.empty:
            return "Koi result nahi mila.", "No result.", None, None, False
        name = s.name if isinstance(s.name, str) else "value"
        table = s.rename(name).reset_index()
        table.columns = [str(c) for c in table.columns]
        if pd.api.types.is_numeric_dtype(s):
            top_k, top_v = s.index[0], s.iloc[0]
            if len(s) == 1:
                hi = f"{label_hi}: {top_k} = {_fmt(top_v)}."
                en = f"{label_en}: {top_k} = {_fmt(top_v)}."
            else:
                parts = ", ".join(f"{k}: {_fmt(v)}" for k, v in s.head(4).items())
                hi = f"{label_hi}: {parts}" + (" …" if len(s) > 4 else "") + "."
                en = f"{label_en}: {parts}" + (" …" if len(s) > 4 else "") + "."
            if 1 < len(s) <= 40:
                x, y = table.columns[0], table.columns[-1]
                chart = px.bar(table, x=x, y=y)
        else:
            parts = ", ".join(map(str, s.head(5).tolist()))
            hi = f"{label_hi}: {parts}."
            en = f"{label_en}: {parts}."
    elif isinstance(result, pd.DataFrame):
        if result.empty:
            return "Koi row nahi mili.", "No matching rows.", None, None, False
        table = result.reset_index() if not isinstance(result.index, pd.RangeIndex) else result
        table.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in table.columns]
        hi = f"{label_hi}: {len(result):,} rows mili (table dekho)."
        en = f"{label_en}: {len(result):,} rows (see table)."
        num_cols = [c for c in table.columns[1:] if pd.api.types.is_numeric_dtype(table[c])]
        if num_cols and len(table) <= 40:
            chart = px.bar(table, x=table.columns[0], y=num_cols[:3], barmode="group")
    elif isinstance(result, (list, tuple)) and len(result) <= 20:
        hi = f"{label_hi}: {', '.join(_fmt(v) for v in result)}."
        en = f"{label_en}: {', '.join(_fmt(v) for v in result)}."
    elif isinstance(result, dict):
        items = list(result.items())[:8]
        hi = f"{label_hi}: " + ", ".join(f"{k} = {_fmt(v)}" for k, v in items) + "."
        en = f"{label_en}: " + ", ".join(f"{k} = {_fmt(v)}" for k, v in items) + "."
        table = pd.DataFrame(items, columns=["item", "value"])
    else:
        hi = f"{label_hi}: {_fmt(result)}."
        en = f"{label_en}: {_fmt(result)}."
    return hi, en, table, chart, True
