"""Shared helpers for report modules.

A module turns one cleaned dataset + the user's parameters into a plain dict:

    {subject, scope, kpis: [...], sections: [{id, title, facts, chart, table}], definitions: [...]}

Everything in it is computed with pandas – the LLM only ever writes prose
around these numbers, it never produces them.
"""
from __future__ import annotations

import math

import pandas as pd


def nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA


def pct(v, d=0) -> str:
    return "–" if nan(v) else f"{v:.{d}f}%"


def cnt(v) -> str:
    return "–" if nan(v) else f"{int(round(v)):,}"


def dec(v, d=1) -> str:
    return "–" if nan(v) else f"{v:.{d}f}"


def money(v, cur="₹") -> str:
    if nan(v):
        return "–"
    body = f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.2f}"
    return f"{cur}{body}" if len(cur) == 1 else f"{cur} {body}"


def trunc(s, n=58) -> str:
    s = "" if nan(s) else str(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def opts(values, labels=None, parents=None):
    out = []
    for i, v in enumerate(values):
        o = {"value": str(v), "label": str(labels[i]) if labels is not None else str(v)}
        if parents is not None:
            o["parent"] = str(parents[i])
        out.append(o)
    return out


def field(key, label, type_, required=False, options=None, help_="", depends_on=None, default=None):
    f = {"key": key, "label": label, "type": type_, "required": required, "help": help_}
    if options is not None:
        f["options"] = options
    if depends_on:
        f["depends_on"] = depends_on
    if default is not None:
        f["default"] = default
    return f


def kpi(label, value, note=""):
    return {"label": label, "value": value, "note": note}


def table(columns, rows, widths=None, align=None):
    """widths: relative column widths. align: 'l'/'r' per column."""
    if align is None:
        align = ["l"] + ["r"] * (len(columns) - 1)
    return {"columns": columns, "rows": [[("" if nan(c) else str(c)) for c in r] for r in rows],
            "widths": widths, "align": align}


def chart(type_, title, labels=None, values=None, fmt="num", **kw):
    labels = [] if labels is None else list(labels)
    values = [] if values is None else list(values)
    c = {"type": type_, "title": title, "labels": [str(x) for x in labels],
         "values": [None if nan(v) else float(v) for v in values], "fmt": fmt}
    c.update(kw)
    return c


def section(id_, title, facts, chart_=None, table_=None):
    return {"id": id_, "title": title, "facts": [f for f in facts if f], "chart": chart_, "table": table_}


def as_list(v):
    if v is None or v == "":
        return []
    return [str(x) for x in v] if isinstance(v, (list, tuple, set)) else [str(v)]


def top_n(params, default=10) -> int:
    try:
        return max(3, min(25, int(params.get("top_n") or default)))
    except (TypeError, ValueError):
        return default


def join_names(items, limit=3) -> str:
    items = [str(i) for i in items][:limit]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]
