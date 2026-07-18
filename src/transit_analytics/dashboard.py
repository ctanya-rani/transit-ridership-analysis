"""Self-contained HTML dashboard for the ridership analytics.

Everything is inlined — CSS, SVG charts, tooltip script — so the output is a
single file that renders offline in light or dark mode.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from html import escape
from pathlib import Path

from . import analytics
from .charts import (
    bar_chart,
    compact_number,
    legend,
    line_chart,
    stat_tile,
    truncate,
)

STYLE = """
:root {
  color-scheme: light;
  --surface-1: #fcfcfb; --page: #f9f9f7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --series-1: #2a78d6; --series-2: #008300;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #008300;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-1: #1a1a19; --page: #0d0d0d;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --series-1: #3987e5; --series-2: #008300;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--page); color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 14px; line-height: 1.45;
}
main { max-width: 1080px; margin: 0 auto; padding: 24px 20px 48px; }
h1 { font-size: 22px; margin: 0 0 2px; }
h2 { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
.subtitle { color: var(--text-secondary); margin: 0 0 20px; }
.subtitle .badge {
  display: inline-block; padding: 1px 8px; border: 1px solid var(--border);
  border-radius: 999px; font-size: 12px; color: var(--text-muted);
}
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px; margin-bottom: 20px; }
.tile { background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px; }
.tile-label { color: var(--text-secondary); font-size: 13px; }
.tile-value { font-size: 30px; font-weight: 600; margin-top: 2px; }
.tile-note { color: var(--text-muted); font-size: 12px; margin-top: 2px; }
.card { background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px 18px; margin-bottom: 16px; }
.card .desc { color: var(--text-muted); font-size: 12.5px; margin: 0 0 10px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 860px) { .grid-2 { grid-template-columns: 1fr; } }
svg { display: block; width: 100%; height: auto; }
svg .grid { stroke: var(--grid); stroke-width: 1; }
svg .axis { stroke: var(--axis); stroke-width: 1; }
svg .tick { fill: var(--text-muted); font-size: 11px;
  font-variant-numeric: tabular-nums; }
svg .bar-label { fill: var(--text-secondary); font-size: 12px; }
svg .bar-value { fill: var(--text-secondary); font-size: 12px;
  font-variant-numeric: tabular-nums; }
svg .crosshair { stroke: var(--axis); stroke-width: 1; }
.bar:hover path, .bar:focus path { opacity: 0.82; }
.legend { display: flex; gap: 16px; margin: 2px 0 8px; color: var(--text-secondary);
  font-size: 12.5px; flex-wrap: wrap; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-key { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
.chart-wrap { position: relative; }
.tooltip {
  position: absolute; pointer-events: none; background: var(--surface-1);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
  font-size: 12.5px; box-shadow: 0 2px 10px rgba(0,0,0,0.12); z-index: 5;
  min-width: 120px;
}
.tooltip .tt-title { color: var(--text-muted); margin-bottom: 4px; }
.tooltip .tt-row { display: flex; align-items: center; gap: 6px; }
.tooltip .tt-key { width: 10px; height: 3px; border-radius: 2px; }
.tooltip .tt-value { font-weight: 600; margin-left: auto; padding-left: 12px;
  font-variant-numeric: tabular-nums; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--grid); }
th { color: var(--text-secondary); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
details summary { cursor: pointer; color: var(--text-secondary); font-size: 13px;
  margin-top: 10px; }
footer { color: var(--text-muted); font-size: 12px; margin-top: 24px; }
"""

SCRIPT = """
document.querySelectorAll('[data-viz="line"]').forEach(function (wrap) {
  var svg = wrap.querySelector('svg');
  var data = JSON.parse(wrap.querySelector('.viz-data').textContent);
  var tooltip = wrap.querySelector('.tooltip');
  var crosshair = svg.querySelector('.crosshair');
  var viewBox = svg.viewBox.baseVal;

  function onMove(evt) {
    var rect = svg.getBoundingClientRect();
    var sx = (evt.clientX - rect.left) * viewBox.width / rect.width;
    var n = data.labels.length;
    var frac = (sx - data.padLeft) / data.plotW;
    var i = Math.round(frac * (n - 1));
    if (i < 0 || i >= n) { onLeave(); return; }
    var px = data.padLeft + data.plotW * i / Math.max(n - 1, 1);
    crosshair.setAttribute('x1', px);
    crosshair.setAttribute('x2', px);
    crosshair.setAttribute('visibility', 'visible');

    tooltip.textContent = '';
    var title = document.createElement('div');
    title.className = 'tt-title';
    title.textContent = data.labels[i];
    tooltip.appendChild(title);
    data.series.forEach(function (s) {
      var row = document.createElement('div');
      row.className = 'tt-row';
      var key = document.createElement('span');
      key.className = 'tt-key';
      key.style.background = 'var(' + s.colorVar + ')';
      var name = document.createElement('span');
      name.textContent = s.name;
      var value = document.createElement('span');
      value.className = 'tt-value';
      value.textContent = s.values[i].toLocaleString();
      row.appendChild(key); row.appendChild(name); row.appendChild(value);
      tooltip.appendChild(row);
    });
    tooltip.hidden = false;
    var wrapRect = wrap.getBoundingClientRect();
    var left = (px / viewBox.width) * wrapRect.width + 12;
    if (left + tooltip.offsetWidth + 16 > wrapRect.width) {
      left -= tooltip.offsetWidth + 24;
    }
    tooltip.style.left = left + 'px';
    tooltip.style.top = '10px';
  }
  function onLeave() {
    tooltip.hidden = true;
    crosshair.setAttribute('visibility', 'hidden');
  }
  svg.addEventListener('pointermove', onMove);
  svg.addEventListener('pointerleave', onLeave);
});

document.querySelectorAll('[data-viz="bar"]').forEach(function (wrap) {
  var tooltip = wrap.querySelector('.tooltip');
  wrap.querySelectorAll('.bar').forEach(function (bar) {
    bar.addEventListener('pointermove', function (evt) {
      tooltip.textContent = '';
      var title = document.createElement('div');
      title.className = 'tt-title';
      title.textContent = bar.dataset.label;
      var row = document.createElement('div');
      row.className = 'tt-row';
      var value = document.createElement('span');
      value.className = 'tt-value';
      value.textContent = bar.dataset.value + ' boardings/day';
      row.appendChild(value);
      tooltip.appendChild(title); tooltip.appendChild(row);
      tooltip.hidden = false;
      var wrapRect = wrap.getBoundingClientRect();
      var left = evt.clientX - wrapRect.left + 14;
      if (left + tooltip.offsetWidth + 16 > wrapRect.width) {
        left -= tooltip.offsetWidth + 28;
      }
      tooltip.style.left = left + 'px';
      tooltip.style.top = (evt.clientY - wrapRect.top + 14) + 'px';
    });
    bar.addEventListener('pointerleave', function () { tooltip.hidden = true; });
  });
});
"""


def render(conn: sqlite3.Connection, title: str = "Transit Ridership Analytics") -> str:
    summary = analytics.system_summary(conn)
    daily = analytics.daily_boardings(conn)
    routes = analytics.boardings_by_route(conn)
    stops = analytics.top_stops(conn, limit=12)
    hourly = analytics.hourly_profile(conn)
    headways = analytics.route_headways(conn)

    source_row = conn.execute(
        "SELECT DISTINCT source FROM ridership LIMIT 2"
    ).fetchall()
    sources = ", ".join(sorted(r["source"] for r in source_row)) or "none"
    agency = conn.execute("SELECT agency_name FROM agency LIMIT 1").fetchone()
    agency_name = agency["agency_name"] if agency else "Unknown agency"

    window = ""
    if daily:
        window = f"{daily[0]['date']} → {daily[-1]['date']}"

    tiles = "".join(
        [
            stat_tile("Total boardings", compact_number(summary["total_boardings"]),
                      f"{summary['days']} service days"),
            stat_tile("Avg weekday boardings",
                      compact_number(summary["avg_weekday_boardings"])),
            stat_tile("Avg weekend boardings",
                      compact_number(summary["avg_weekend_boardings"])),
            stat_tile("Busiest route",
                      summary["busiest_route"]["short_name"]
                      if summary["busiest_route"] else "—",
                      f"{compact_number(summary['busiest_route']['avg_daily_boardings'])}"
                      f"/day" if summary["busiest_route"] else ""),
            stat_tile("Network", f"{summary['n_routes']} routes",
                      f"{summary['n_stops']} stops"),
        ]
    )

    daily_chart = line_chart(
        [{"name": "Boardings", "color_var": "--series-1",
          "values": [d["boardings"] for d in daily]}],
        x_labels=[d["date"][5:] for d in daily],
        chart_id="daily",
    )
    hourly_chart = line_chart(
        [
            {"name": "Weekday", "color_var": "--series-1",
             "values": [h["weekday"] for h in hourly]},
            {"name": "Weekend", "color_var": "--series-2",
             "values": [h["weekend"] for h in hourly]},
        ],
        x_labels=[f"{h['hour']:02d}" for h in hourly],
        x_tick_every=3,
        chart_id="hourly",
    )
    route_bars = bar_chart(
        [(truncate(f"{r['short_name']} · {r['long_name']}"), r["avg_daily_boardings"])
         for r in routes],
        chart_id="routes",
    )
    stop_bars = bar_chart(
        [(truncate(s["stop_name"]), s["avg_daily_boardings"]) for s in stops],
        chart_id="stops",
    )

    headway_rows = "".join(
        f"<tr><td>{escape(h['short_name'])}</td>"
        f"<td class='num'>{h['trips_per_weekday']}</td>"
        f"<td class='num'>{h['min_headway_min']}</td>"
        f"<td class='num'>{h['median_headway_min']}</td>"
        f"<td>{escape(h['span'])}</td></tr>"
        for h in headways
    )
    route_table_rows = "".join(
        f"<tr><td>{escape(str(r['short_name']))}</td>"
        f"<td>{escape(str(r['long_name']))}</td>"
        f"<td class='num'>{r['avg_daily_boardings']:,}</td>"
        f"<td class='num'>{r['trips_per_day']}</td>"
        f"<td class='num'>{r['boardings_per_trip']}</td>"
        f"<td class='num'>{r['boardings_per_revenue_hour'] or '—'}</td></tr>"
        for r in routes
    )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{STYLE}</style>
</head>
<body>
<main>
<h1>{escape(title)}</h1>
<p class="subtitle">{escape(agency_name)} · {escape(window)} ·
<span class="badge">ridership source: {escape(sources)}</span></p>

<div class="tiles">{tiles}</div>

<div class="card">
  <h2>Daily boardings</h2>
  <p class="desc">Systemwide boardings per service day. Weekend dips and the
  holiday exception are visible in the trace.</p>
  {daily_chart}
</div>

<div class="card">
  <h2>Boardings by hour of day</h2>
  <p class="desc">Average boardings per hour, weekday vs weekend.</p>
  {legend([("Weekday", "--series-1"), ("Weekend", "--series-2")])}
  {hourly_chart}
</div>

<div class="grid-2">
  <div class="card">
    <h2>Average daily boardings by route</h2>
    {route_bars}
  </div>
  <div class="card">
    <h2>Busiest stops</h2>
    {stop_bars}
  </div>
</div>

<div class="card">
  <h2>Route performance</h2>
  <table>
    <thead><tr><th>Route</th><th>Corridor</th>
    <th class="num">Boardings/day</th><th class="num">Trips/day</th>
    <th class="num">Boardings/trip</th><th class="num">Boardings/rev-hr</th></tr></thead>
    <tbody>{route_table_rows}</tbody>
  </table>
  <details>
    <summary>Scheduled weekday headways</summary>
    <table>
      <thead><tr><th>Route</th><th class="num">Trips/weekday</th>
      <th class="num">Min headway (min)</th><th class="num">Median headway (min)</th>
      <th>Service span</th></tr></thead>
      <tbody>{headway_rows}</tbody>
    </table>
  </details>
</div>

<footer>Generated {generated} by transit-analytics. Simulated ridership is
modeled from the schedule and clearly labeled; load real APC data with
<code>transit-analytics load-apc</code>.</footer>
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""


def write(conn: sqlite3.Connection, out_path: str | Path,
          title: str = "Transit Ridership Analytics") -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(conn, title=title), encoding="utf-8")
    return out
