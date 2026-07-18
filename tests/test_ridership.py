from datetime import date

import pytest

from transit_analytics import gtfs, ridership


def _simulate(conn, days=7, seed=42):
    return ridership.simulate(conn, start=date(2026, 3, 2), days=days, seed=seed)


def test_simulate_writes_records(tiny_db):
    written = _simulate(tiny_db)
    assert written > 0
    n = tiny_db.execute("SELECT COUNT(*) AS n FROM ridership").fetchone()["n"]
    assert n == written


def test_simulate_loads_are_consistent(tiny_db):
    _simulate(tiny_db)
    for day_trip in tiny_db.execute(
        "SELECT DISTINCT service_date, trip_id FROM ridership"
    ):
        rows = tiny_db.execute(
            "SELECT boardings, alightings, load FROM ridership "
            "WHERE service_date=? AND trip_id=? ORDER BY stop_sequence",
            (day_trip["service_date"], day_trip["trip_id"]),
        ).fetchall()
        load = 0
        for row in rows:
            load += row["boardings"] - row["alightings"]
            assert row["load"] == load
            assert load >= 0
        # Everyone alights by the end of the trip.
        assert load == 0
        assert rows[-1]["boardings"] == 0


def test_simulate_is_deterministic(tiny_feed_dir):
    def run():
        conn = gtfs.connect(":memory:")
        gtfs.load_feed(tiny_feed_dir, conn)
        _simulate(conn)
        return conn.execute(
            "SELECT service_date, trip_id, stop_sequence, boardings, alightings "
            "FROM ridership ORDER BY service_date, trip_id, stop_sequence"
        ).fetchall()

    first, second = run(), run()
    assert [tuple(r) for r in first] == [tuple(r) for r in second]


def test_simulate_respects_calendar(tiny_db):
    _simulate(tiny_db, days=7)
    # Saturday trips (T3) only appear on the Saturday.
    dates = {
        row["service_date"]
        for row in tiny_db.execute(
            "SELECT DISTINCT service_date FROM ridership WHERE trip_id='T3'"
        )
    }
    assert dates == {"2026-03-07"}


def test_simulate_replace_avoids_duplication(tiny_db):
    first = _simulate(tiny_db)
    second = _simulate(tiny_db)
    assert first == second
    n = tiny_db.execute("SELECT COUNT(*) AS n FROM ridership").fetchone()["n"]
    assert n == second


def test_load_apc_csv(tiny_db, tmp_path):
    csv_path = tmp_path / "apc.csv"
    csv_path.write_text(
        "service_date,trip_id,stop_id,stop_sequence,boardings,alightings\n"
        "2026-03-02,T1,A,1,10,0\n"
        "2026-03-02,T1,B,2,5,3\n"
        "2026-03-02,T1,C,3,0,12\n",
        encoding="utf-8",
    )
    written = ridership.load_apc_csv(tiny_db, csv_path)
    assert written == 3
    rows = tiny_db.execute(
        "SELECT load, source FROM ridership ORDER BY stop_sequence"
    ).fetchall()
    assert [r["load"] for r in rows] == [10, 12, 0]
    assert all(r["source"] == "apc" for r in rows)


def test_load_apc_csv_missing_columns(tiny_db, tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("trip_id,boardings\nT1,5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        ridership.load_apc_csv(tiny_db, csv_path)
