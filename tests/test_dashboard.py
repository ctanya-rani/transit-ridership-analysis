from datetime import date

from transit_analytics import dashboard, ridership
from transit_analytics.charts import _nice_ticks, bar_chart, line_chart, truncate


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
