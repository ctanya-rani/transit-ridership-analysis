import textwrap
import zipfile
from datetime import date, timedelta

import pytest

from transit_analytics import gtfs


def _write_files(dir_path, files: dict[str, str]) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (dir_path / name).write_text(textwrap.dedent(content), encoding="utf-8")


def test_parse_gtfs_time_basic():
    assert gtfs.parse_gtfs_time("08:15:30") == 8 * 3600 + 15 * 60 + 30


def test_parse_gtfs_time_past_midnight():
    assert gtfs.parse_gtfs_time("25:10:00") == 25 * 3600 + 10 * 60


def test_parse_gtfs_time_empty_is_none():
    assert gtfs.parse_gtfs_time("") is None
    assert gtfs.parse_gtfs_time("  ") is None


@pytest.mark.parametrize("bad", ["8:15", "08:61:00", "abc", "-1:00:00"])
def test_parse_gtfs_time_invalid(bad):
    with pytest.raises(ValueError):
        gtfs.parse_gtfs_time(bad)


def test_format_round_trip():
    assert gtfs.format_gtfs_time(gtfs.parse_gtfs_time("26:05:07")) == "26:05:07"


def test_load_feed_from_directory(tiny_db):
    counts = {
        row["name"]: tiny_db.execute(f"SELECT COUNT(*) AS n FROM {row['name']}").fetchone()["n"]
        for row in tiny_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert counts["routes"] == 1
    assert counts["stops"] == 3
    assert counts["trips"] == 3
    assert counts["stop_times"] == 9
    assert counts["calendar"] == 2


def test_load_feed_from_zip(tiny_feed_dir, tmp_path):
    zip_path = tmp_path / "feed.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for txt in tiny_feed_dir.glob("*.txt"):
            zf.write(txt, txt.name)
    conn = gtfs.connect(":memory:")
    counts = gtfs.load_feed(zip_path, conn)
    assert counts["stop_times"] == 9


def test_load_feed_missing_path(tmp_path):
    conn = gtfs.connect(":memory:")
    with pytest.raises(FileNotFoundError):
        gtfs.load_feed(tmp_path / "nope.zip", conn)


def test_service_ids_weekday(tiny_db):
    # 2026-03-02 is a Monday
    assert gtfs.service_ids_on(tiny_db, date(2026, 3, 2)) == {"WEEKDAY"}


def test_service_ids_saturday(tiny_db):
    # 2026-03-07 is a Saturday
    assert gtfs.service_ids_on(tiny_db, date(2026, 3, 7)) == {"SATURDAY"}


def test_service_ids_holiday_exception(tiny_db):
    # 2026-03-20 is a Friday, swapped to SATURDAY service by calendar_dates
    assert gtfs.service_ids_on(tiny_db, date(2026, 3, 20)) == {"SATURDAY"}


def test_stop_times_store_seconds(tiny_db):
    row = tiny_db.execute(
        "SELECT departure_secs FROM stop_times WHERE trip_id='T3' AND stop_sequence=1"
    ).fetchone()
    assert row["departure_secs"] == 25 * 3600 + 10 * 60


# --- validate_feed / load_feed error handling -------------------------------


def test_validate_feed_missing_required_files(tmp_path):
    feed = tmp_path / "feed"
    _write_files(feed, {
        "routes.txt": "route_id\nR1\n",
        "stops.txt": "stop_id,stop_name\nS1,Stop\n",
    })
    conn = gtfs.connect(":memory:")
    with pytest.raises(gtfs.GTFSValidationError, match="missing required file"):
        gtfs.load_feed(feed, conn)


def test_validate_feed_missing_calendar_source(tmp_path):
    feed = tmp_path / "feed"
    _write_files(feed, {
        "routes.txt": "route_id\nR1\n",
        "stops.txt": "stop_id,stop_name\nS1,Stop\n",
        "trips.txt": "trip_id,route_id,service_id\nT1,R1,WD\n",
        "stop_times.txt": "trip_id,stop_id,stop_sequence\nT1,S1,1\n",
    })
    conn = gtfs.connect(":memory:")
    with pytest.raises(gtfs.GTFSValidationError, match="calendar"):
        gtfs.load_feed(feed, conn)


def test_validate_feed_missing_column(tmp_path):
    feed = tmp_path / "feed"
    _write_files(feed, {
        "routes.txt": "route_short_name\nX\n",  # missing route_id
        "stops.txt": "stop_id,stop_name\nS1,Stop\n",
        "trips.txt": "trip_id,route_id,service_id\nT1,R1,WD\n",
        "stop_times.txt": "trip_id,stop_id,stop_sequence\nT1,S1,1\n",
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,"
            "sunday,start_date,end_date\nWD,1,1,1,1,1,0,0,20260101,20261231\n"
        ),
    })
    conn = gtfs.connect(":memory:")
    with pytest.raises(gtfs.GTFSValidationError, match="route_id"):
        gtfs.load_feed(feed, conn)


def test_validate_feed_bad_zip(tmp_path):
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not actually a zip archive")
    conn = gtfs.connect(":memory:")
    with pytest.raises(gtfs.GTFSValidationError, match="not a valid"):
        gtfs.load_feed(bad_zip, conn)


def test_load_feed_wrapper_folder_in_zip(tiny_feed_dir, tmp_path):
    """Some exports zip with a wrapper folder (gtfs_export/routes.txt) — still loads."""
    zip_path = tmp_path / "wrapped.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for txt in tiny_feed_dir.glob("*.txt"):
            zf.write(txt, f"gtfs_export/{txt.name}")
    conn = gtfs.connect(":memory:")
    counts = gtfs.load_feed(zip_path, conn)
    assert counts["stop_times"] == 9


# --- feed_date_bounds / pick_simulation_window ------------------------------


def test_feed_date_bounds(tiny_db):
    assert gtfs.feed_date_bounds(tiny_db) == (date(2026, 1, 1), date(2026, 12, 31))


def test_feed_date_bounds_empty_db():
    conn = gtfs.connect(":memory:")
    assert gtfs.feed_date_bounds(conn) is None


def test_pick_simulation_window_within_bounds(tiny_db):
    start, days = gtfs.pick_simulation_window(tiny_db, preferred_days=28)
    assert days == 28
    assert date(2026, 1, 1) <= start
    assert start + timedelta(days=days - 1) <= date(2026, 12, 31)
    assert start.weekday() == 0  # prefers a Monday when one is reachable


def test_pick_simulation_window_clamped_to_short_feed(tmp_path):
    feed = tmp_path / "feed"
    _write_files(feed, {
        "routes.txt": "route_id\nR1\n",
        "stops.txt": "stop_id,stop_name\nS1,Stop\n",
        "trips.txt": "trip_id,route_id,service_id\nT1,R1,WD\n",
        "stop_times.txt": (
            "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
            "T1,S1,1,08:00:00,08:00:00\n"
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,"
            "sunday,start_date,end_date\nWD,1,1,1,1,1,1,1,20260601,20260605\n"
        ),
    })
    conn = gtfs.connect(":memory:")
    gtfs.load_feed(feed, conn)
    start, days = gtfs.pick_simulation_window(conn, preferred_days=28)
    assert days == 5
    assert start == date(2026, 6, 1)
    assert start + timedelta(days=days - 1) == date(2026, 6, 5)


def test_pick_simulation_window_no_calendar_data():
    conn = gtfs.connect(":memory:")
    start, days = gtfs.pick_simulation_window(conn, preferred_days=28)
    assert days == 28
    assert start == date.today()
