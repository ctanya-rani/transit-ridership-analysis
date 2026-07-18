import sqlite3
import textwrap
from pathlib import Path

import pytest

from transit_analytics import gtfs

TINY_FEED = {
    "agency.txt": """\
        agency_id,agency_name,agency_url,agency_timezone
        T,Tiny Transit,https://example.org,America/Los_Angeles
        """,
    "routes.txt": """\
        route_id,agency_id,route_short_name,route_long_name,route_type,route_color
        R1,T,R1,Downtown - Uptown,3,2A78D6
        """,
    "stops.txt": """\
        stop_id,stop_name,stop_lat,stop_lon
        A,Downtown,47.60,-122.33
        B,Midtown,47.62,-122.32
        C,Uptown,47.64,-122.31
        """,
    "trips.txt": """\
        trip_id,route_id,service_id,trip_headsign,direction_id
        T1,R1,WEEKDAY,Uptown,0
        T2,R1,WEEKDAY,Uptown,0
        T3,R1,SATURDAY,Uptown,0
        """,
    "stop_times.txt": """\
        trip_id,arrival_time,departure_time,stop_id,stop_sequence
        T1,08:00:00,08:00:00,A,1
        T1,08:10:00,08:10:30,B,2
        T1,08:20:00,08:20:00,C,3
        T2,17:00:00,17:00:00,A,1
        T2,17:10:00,17:10:30,B,2
        T2,17:20:00,17:20:00,C,3
        T3,25:10:00,25:10:00,A,1
        T3,25:20:00,25:20:30,B,2
        T3,25:30:00,25:30:00,C,3
        """,
    "calendar.txt": """\
        service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
        WEEKDAY,1,1,1,1,1,0,0,20260101,20261231
        SATURDAY,0,0,0,0,0,1,0,20260101,20261231
        """,
    "calendar_dates.txt": """\
        service_id,date,exception_type
        WEEKDAY,20260320,2
        SATURDAY,20260320,1
        """,
}


@pytest.fixture
def tiny_feed_dir(tmp_path: Path) -> Path:
    feed = tmp_path / "tiny_gtfs"
    feed.mkdir()
    for name, content in TINY_FEED.items():
        (feed / name).write_text(textwrap.dedent(content), encoding="utf-8")
    return feed


@pytest.fixture
def tiny_db(tiny_feed_dir: Path) -> sqlite3.Connection:
    conn = gtfs.connect(":memory:")
    gtfs.load_feed(tiny_feed_dir, conn)
    return conn
