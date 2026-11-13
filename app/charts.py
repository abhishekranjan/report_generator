"""Render the declarative chart specs produced by modules into PNG bytes."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Categorical slots (fixed order), ink and chrome.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
BLUE, BLUE_SOFT, BLUE_DEEP = "#2a78d6", "#9ec5f4", "#1c5cab"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "xtick.color": MUTED, "ytick.color": INK2,
    "xtick.labelsize": 8, "ytick.labelsize": 8.5, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "legend.frameon": False, "legend.fontsize": 8.5,
})


def fmt_value(v, fmt):
    if v is None:
        return ""
    if fmt == "pct":
        return f"{v:.0f}%"
    if fmt == "pct1":
        return f"{v:.1f}%"
    if fmt == "dec":
        return f"{v:.1f}"
    return f"{v:,.0f}"


def _title(ax, text):
    ax.set_title(text, loc="left", fontsize=10.5, fontweight="bold", color=INK, pad=12)


def _barh(c):
    labels, values = c["labels"], [v or 0 for v in c["values"]]
    fig, ax = plt.subplots(figsize=(7.2, max(1.9, 0.34 * len(labels) + 1.0)))
    hi = c.get("highlight")
    colors = [(BLUE_DEEP if l == hi else BLUE_SOFT) for l in labels] if hi in labels else BLUE
    y = range(len(labels))
    ax.barh(y, values, color=colors, height=0.62)
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    vmax = max(values) if values else 1
    ax.set_xlim(0, c.get("xmax") or vmax * 1.14 or 1)
    for i, v in enumerate(values):
        ax.text(v + (ax.get_xlim()[1] * 0.012), i, fmt_value(v, c["fmt"]), va="center", ha="left", fontsize=8.5, color=INK2,
                fontweight="bold" if labels[i] == hi else "normal")
    ax.xaxis.set_major_formatter(lambda v, _: fmt_value(v, "pct" if c["fmt"].startswith("pct") else c["fmt"]))
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)
    _title(ax, c["title"])
    return fig


def _bar(c):
    labels, values = c["labels"], [v or 0 for v in c["values"]]
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    x = range(len(labels))
    ax.bar(x, values, color=BLUE, width=0.58)
    ax.set_xticks(list(x), labels)
    ax.tick_params(axis="x", colors=INK2, length=0, labelsize=8.5)
    vmax = max(values) if values else 1
    ax.set_ylim(0, vmax * 1.16 or 1)
    for i, v in enumerate(values):
        ax.text(i, v + vmax * 0.02, fmt_value(v, c["fmt"]), ha="center", va="bottom", fontsize=8.5, color=INK2)
    ax.yaxis.set_major_formatter(lambda v, _: fmt_value(v, c["fmt"]))
    ax.grid(axis="y", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, colors=MUTED)
    _title(ax, c["title"])
    return fig


def _stacked(c):
    labels = c["labels"]
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    x = range(len(labels))
    bottom = [0.0] * len(labels)
    for i, (name, vals) in enumerate(c["series"].items()):
        vals = [v or 0 for v in vals]
        ax.bar(x, vals, bottom=bottom, color=SERIES[i % len(SERIES)], width=0.5, label=name,
               edgecolor=SURFACE, linewidth=1.5)
        for j, v in enumerate(vals):
            if v > 0.08 * max(1, max(b + w for b, w in zip(bottom, vals))):
                ax.text(j, bottom[j] + v / 2, fmt_value(v, c["fmt"]), ha="center", va="center", fontsize=8.5,
                        color="#ffffff", fontweight="bold")
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xticks(list(x), labels)
    ax.tick_params(axis="x", colors=INK2, length=0, labelsize=8.5)
    ax.yaxis.set_major_formatter(lambda v, _: fmt_value(v, c["fmt"]))
    ax.grid(axis="y", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, colors=MUTED)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.02), ncols=4, handlelength=1, columnspacing=1.4, borderaxespad=0)
    ax.set_ylim(0, max(bottom) * 1.2 if bottom else 1)
    _title(ax, c["title"])
    return fig


def _line(c):
    labels = c["labels"]
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    x = list(range(len(labels)))
    ends = []
    for i, (name, vals) in enumerate(c["series"].items()):
        ys = [float("nan") if v is None else v for v in vals]
        col = SERIES[i % len(SERIES)]
        ax.plot(x, ys, color=col, linewidth=2, marker="o", markersize=3.5, label=name)
        last = [(xi, yi) for xi, yi in zip(x, ys) if yi == yi]
        if last:
            ends.append((last[-1][1], fmt_value(last[-1][1], c["fmt"]), last[-1][0]))
    for yv, txt, xv in ends:  # direct value label at each series end; identity is in the legend
        ax.annotate(txt, (xv, yv), xytext=(6, 0), textcoords="offset points", va="center", fontsize=8.5, color=INK2)
    if c.get("invert"):
        ax.invert_yaxis()
    step = max(1, len(labels) // 6)
    ax.set_xticks(x[::step], labels[::step])
    ax.set_xlim(-0.3, len(labels) - 1 + 0.9)
    ax.grid(axis="y", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2, handlelength=1.4, columnspacing=1.4, borderaxespad=0)
    ax.set_title(c["title"], loc="left", fontsize=10.5, fontweight="bold", color=INK, pad=12 + 14 * ((len(c["series"]) + 1) // 2))
    return fig


RENDERERS = {"barh": _barh, "bar": _bar, "stacked": _stacked, "line": _line}


def render(spec) -> tuple[bytes, float]:
    """Return (png bytes, height/width ratio)."""
    fig = RENDERERS[spec["type"]](spec)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200)
    w, h = fig.get_size_inches()
    plt.close(fig)
    return buf.getvalue(), h / w
