import json
from datetime import date

from transit_analytics import dashboard, ridership
from transit_analytics.charts import (
    _nice_ticks,
    bar_chart,
    line_chart,
    safe_json,
    truncate,
)


def test_nice_ticks_cover_max():
    for max_v in (7, 99, 101, 113_000, 127_450, 1):
        ticks = _nice_ticks(max_v)
        assert ticks[0] == 0
        assert ticks[-1] >= max_v, (max_v, ticks)


def test_truncate():
    assert truncate("short") == "short"
    assert truncate("x" * 40, 30).endswith("…")
    assert len(truncate("x" * 40, 30)) == 30


def test_line_chart_escapes_and_embeds_data():
    html = line_chart(
        [{"name": "A", "color_var": "--series-1", "values": [1, 2, 3]}],
        x_labels=["<b>", "y", "z"],
    )
    assert "&lt;b&gt;" in html
    assert '"values": [1, 2, 3]' in html
    assert 'data-viz="line"' in html


def test_bar_chart_escapes_labels():
    html = bar_chart([("<script>", 5.0)])
    assert "<script>" not in html.replace('<script type="application/json"', "")
    assert "&lt;script&gt;" in html


def test_dashboard_renders(tiny_db, tmp_path):
    ridership.simulate(tiny_db, start=date(2026, 3, 2), days=7, seed=1)
    out = dashboard.write(tiny_db, tmp_path / "dash.html")
    html = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "Daily boardings" in html
    assert "Tiny Transit" in html
    assert "ridership source: simulated" in html
    # Theme-aware tokens present for both modes.
    assert "prefers-color-scheme: dark" in html
    assert '[data-theme="dark"]' in html


def test_safe_json_escapes_script_close_tag():
    encoded = safe_json({"name": "</script><script>alert(1)</script>"})
    assert "</script>" not in encoded
    # Still round-trips to the original value through JSON.parse's rules
    # (\/ is a valid escaped solidus per the JSON spec).
    assert json.loads(encoded.replace("<\\/", "</"))["name"] == (
        "</script><script>alert(1)</script>"
    )


def test_line_chart_rotates_long_x_labels_only():
    long = line_chart(
        [{"name": "A", "color_var": "--series-1", "values": [1, 2, 3]}],
        x_labels=["Downtown Seattle", "Midtown Junction", "Uptown Terminal"],
    )
    assert "rotate(-40" in long

    short = line_chart(
        [{"name": "A", "color_var": "--series-1", "values": [1, 2, 3]}],
        x_labels=["00", "12", "23"],
    )
    assert "rotate(-40" not in short


def test_dashboard_includes_export_data_and_route_picker(tiny_db, tmp_path):
    ridership.simulate(tiny_db, start=date(2026, 3, 2), days=7, seed=1)
    html = dashboard.render(tiny_db)
    assert 'id="export-data"' in html
    assert 'id="route-picker"' in html
    assert 'data-export="daily"' in html
    assert 'data-export="routes"' in html
    assert 'data-export="stops"' in html
    assert "table-scroll" in html

    marker = 'id="export-data">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    payload = json.loads(html[start:end].replace("<\\/", "</"))
    assert set(payload) == {"daily", "routes", "stops"}
    assert payload["routes"][0]["route_id"] == "R1"
