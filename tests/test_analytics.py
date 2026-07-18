import sqlite3

import pytest

from transit_analytics import analytics


@pytest.fixture
def seeded_db(tiny_db) -> sqlite3.Connection:
    """Hand-written ridership rows: a weekday (Mon 03-02) and a Saturday (03-07)."""
    rows = [
        # date, trip, stop, seq, boardings, alightings, load
        ("2026-03-02", "T1", "A", 1, 10, 0, 10),
        ("2026-03-02", "T1", "B", 2, 6, 4, 12),
        ("2026-03-02", "T1", "C", 3, 0, 12, 0),
        ("2026-03-02", "T2", "A", 1, 20, 0, 20),
        ("2026-03-02", "T2", "B", 2, 2, 10, 12),
        ("2026-03-02", "T2", "C", 3, 0, 12, 0),
        ("2026-03-07", "T3", "A", 1, 4, 0, 4),
        ("2026-03-07", "T3", "B", 2, 2, 1, 5),
        ("2026-03-07", "T3", "C", 3, 0, 5, 0),
    ]
    tiny_db.executemany(
        "INSERT INTO ridership VALUES (?, ?, ?, ?, ?, ?, ?, 'simulated')", rows
    )
    return tiny_db


def test_daily_boardings(seeded_db):
    daily = analytics.daily_boardings(seeded_db)
    assert [(d["date"], d["boardings"], d["is_weekend"]) for d in daily] == [
        ("2026-03-02", 38, False),
        ("2026-03-07", 6, True),
    ]


def test_system_summary(seeded_db):
    summary = analytics.system_summary(seeded_db)
    assert summary["days"] == 2
    assert summary["total_boardings"] == 44
    assert summary["avg_weekday_boardings"] == 38
    assert summary["avg_weekend_boardings"] == 6
    assert summary["busiest_stop"]["stop_id"] == "A"


def test_boardings_by_route(seeded_db):
    routes = analytics.boardings_by_route(seeded_db)
    assert len(routes) == 1
    r = routes[0]
    assert r["route_id"] == "R1"
    # 44 boardings over 2 service days
    assert r["avg_daily_boardings"] == 22
    # 3 trips over 2 days
    assert r["trips_per_day"] == 1.5
    assert r["boardings_per_trip"] == pytest.approx(44 / 3, abs=0.05)


def test_top_stops(seeded_db):
    stops = analytics.top_stops(seeded_db)
    assert stops[0]["stop_id"] == "A"
    assert stops[0]["avg_daily_boardings"] == 17  # (10+20+4)/2
    assert stops[-1]["avg_daily_alightings"] == round(29 / 2)  # stop C


def test_hourly_profile(seeded_db):
    profile = analytics.hourly_profile(seeded_db)
    assert len(profile) == 24
    by_hour = {p["hour"]: p for p in profile}
    # Weekday: T1 boards 16 in hour 8, T2 boards 22 in hour 17.
    assert by_hour[8]["weekday"] == 16
    assert by_hour[17]["weekday"] == 22
    # Saturday trip T3 runs 25:xx -> hour 1 after midnight wrap.
    assert by_hour[1]["weekend"] == 6


def test_route_headways(seeded_db):
    headways = analytics.route_headways(seeded_db)
    assert len(headways) == 1
    h = headways[0]
    assert h["trips_per_weekday"] == 2
    # T1 08:00 -> T2 17:00 = 540 minutes
    assert h["median_headway_min"] == 540
    assert h["span"] == "08:00–17:00"


def test_route_load_profile(seeded_db):
    profile = analytics.route_load_profile(seeded_db, "R1", direction_id=0)
    assert [p["stop_name"] for p in profile] == ["Downtown", "Midtown", "Uptown"]
    assert profile[-1]["avg_load"] == 0


def test_empty_db_summary(tiny_db):
    summary = analytics.system_summary(tiny_db)
    assert summary["days"] == 0
    assert summary["total_boardings"] == 0
    assert analytics.boardings_by_route(tiny_db) == []
    assert analytics.top_stops(tiny_db) == []
