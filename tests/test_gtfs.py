import zipfile
from datetime import date

import pytest

from transit_analytics import gtfs


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
