"""Inline-SVG chart builders for the dashboard.

Marks follow a fixed spec: 2px lines with round joins, bars capped at 24px
with a 4px rounded data-end (square at the baseline), hairline gridlines,
markers with a 2px surface ring. Colors are CSS custom properties so the
same SVG renders correctly on light and dark surfaces. Interactivity
(crosshair + tooltip on lines, per-mark tooltips on bars) is driven by data
attributes consumed by the dashboard's shared script.
"""

from __future__ import annotations

import json
from html import escape

BAR_MAX_THICKNESS = 24
BAR_GAP = 8


def _nice_ticks(max_value: float, n: int = 4) -> list[int]:
    """Round tick steps to 1/2/2.5/5 x 10^k so axis labels are clean."""
    if max_value <= 0:
        return [0, 1]
    rough = max_value / n
    magnitude = 10 ** len(str(int(rough))) / 10
    for mult in (1, 2, 2.5, 5, 10):
        step = magnitude * mult
        if step * n >= max_value:
            break
    ticks = [0]
    value = 0.0
    while value < max_value:  # last tick always covers the max
        value += step
        ticks.append(int(value))
    return ticks


def _fmt(value: float) -> str:
    return f"{value:,.0f}"


def truncate(text: str, limit: int = 30) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def line_chart(
    series: list[dict],
    x_labels: list[str],
    width: int = 720,
    height: int = 260,
    x_tick_every: int | None = None,
    chart_id: str = "line",
) -> str:
    """Multi-series line chart. series: [{name, color_var, values}]."""
    pad_left, pad_right, pad_top, pad_bottom = 56, 16, 12, 28
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    n = len(x_labels)
    max_v = max((max(s["values"]) for s in series if s["values"]), default=1) or 1
    ticks = _nice_ticks(max_v)
    scale_max = ticks[-1] or 1

    def x_at(i: int) -> float:
        return pad_left + (plot_w * i / max(n - 1, 1))

    def y_at(v: float) -> float:
        return pad_top + plot_h * (1 - v / scale_max)

    grid = "".join(
        f'<line x1="{pad_left}" y1="{y_at(t):.1f}" x2="{width - pad_right}" '
        f'y2="{y_at(t):.1f}" class="grid"/>'
        f'<text x="{pad_left - 8}" y="{y_at(t) + 4:.1f}" class="tick" '
        f'text-anchor="end">{_fmt(t)}</text>'
        for t in ticks
    )
    every = x_tick_every or max(1, n // 8)
    x_axis = "".join(
        f'<text x="{x_at(i):.1f}" y="{height - 8}" class="tick" '
        f'text-anchor="middle">{escape(str(lbl))}</text>'
        for i, lbl in enumerate(x_labels)
        if i % every == 0
    )
    paths = []
    for s in series:
        points = " ".join(
            f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(s["values"])
        )
        paths.append(
            f'<polyline points="{points}" fill="none" '
            f'stroke="var({s["color_var"]})" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        # End marker with a surface ring, plus a sparing direct end-label.
        last_i = len(s["values"]) - 1
        if last_i >= 0:
            cx, cy = x_at(last_i), y_at(s["values"][last_i])
            paths.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="var(--surface-1)"/>'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" '
                f'fill="var({s["color_var"]})"/>'
            )
    payload = {
        "labels": [str(l) for l in x_labels],
        "series": [
            {"name": s["name"], "colorVar": s["color_var"], "values": s["values"]}
            for s in series
        ],
        "padLeft": pad_left,
        "plotW": plot_w,
        "padTop": pad_top,
        "plotH": plot_h,
        "scaleMax": scale_max,
    }
    return (
        f'<div class="chart-wrap" data-viz="line" id="{escape(chart_id)}">'
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'preserveAspectRatio="xMidYMid meet">'
        f"{grid}{x_axis}"
        f'<line x1="{pad_left}" y1="{pad_top + plot_h}" x2="{width - pad_right}" '
        f'y2="{pad_top + plot_h}" class="axis"/>'
        f"{''.join(paths)}"
        f'<line class="crosshair" x1="0" x2="0" y1="{pad_top}" '
        f'y2="{pad_top + plot_h}" visibility="hidden"/>'
        f"</svg>"
        f'<script type="application/json" class="viz-data">'
        f"{json.dumps(payload)}</script>"
        f'<div class="tooltip" hidden></div>'
        f"</div>"
    )


def bar_chart(
    items: list[tuple[str, float]],
    color_var: str = "--series-1",
    width: int = 720,
    label_width: int = 210,
    chart_id: str = "bars",
) -> str:
    """Horizontal bar chart with value labels at the bar tips."""
    n = len(items)
    if n == 0:
        return '<p class="empty">No data.</p>'
    thickness = min(BAR_MAX_THICKNESS, 20)
    row_h = thickness + BAR_GAP
    pad_top, pad_bottom = 6, 6
    height = pad_top + pad_bottom + row_h * n
    max_v = max(v for _, v in items) or 1
    value_space = 64
    plot_w = width - label_width - value_space - 12
    bars = []
    for i, (label, value) in enumerate(items):
        y = pad_top + i * row_h + BAR_GAP / 2
        bar_w = max(plot_w * value / max_v, 2)
        x0 = label_width
        r = min(4, bar_w / 2)
        # Square at the baseline (left), 4px rounded data-end (right).
        path = (
            f"M{x0},{y} h{bar_w - r:.1f} q{r},0 {r},{r} v{thickness - 2 * r} "
            f"q0,{r} -{r},{r} h-{bar_w - r:.1f} z"
        )
        bars.append(
            f'<g class="bar" data-label="{escape(label)}" '
            f'data-value="{_fmt(value)}">'
            f'<rect x="0" y="{y - BAR_GAP / 2}" width="{width}" height="{row_h}" '
            f'fill="transparent"/>'
            f'<path d="{path}" fill="var({color_var})"/>'
            f'<text x="{label_width - 10}" y="{y + thickness / 2 + 4}" '
            f'class="bar-label" text-anchor="end">{escape(label)}</text>'
            f'<text x="{x0 + bar_w + 8:.1f}" y="{y + thickness / 2 + 4}" '
            f'class="bar-value">{_fmt(value)}</text>'
            f"</g>"
        )
    return (
        f'<div class="chart-wrap" data-viz="bar" id="{escape(chart_id)}">'
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'preserveAspectRatio="xMidYMid meet">'
        f'<line x1="{label_width}" y1="{pad_top}" x2="{label_width}" '
        f'y2="{height - pad_bottom}" class="axis"/>'
        f"{''.join(bars)}"
        f"</svg>"
        f'<div class="tooltip" hidden></div>'
        f"</div>"
    )


def legend(entries: list[tuple[str, str]]) -> str:
    """Legend row: entries of (name, color_var). Line-style keys."""
    items = "".join(
        f'<span class="legend-item">'
        f'<span class="legend-key" style="background:var({color_var})"></span>'
        f"{escape(name)}</span>"
        for name, color_var in entries
    )
    return f'<div class="legend">{items}</div>'


def stat_tile(label: str, value: str, note: str = "") -> str:
    note_html = f'<div class="tile-note">{escape(note)}</div>' if note else ""
    return (
        f'<div class="tile"><div class="tile-label">{escape(label)}</div>'
        f'<div class="tile-value">{escape(value)}</div>{note_html}</div>'
    )


def compact_number(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"
