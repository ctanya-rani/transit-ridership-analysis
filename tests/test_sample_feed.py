from datetime import date

import pytest

from transit_analytics import gtfs, sample_feed


@pytest.fixture(scope="module")
def sample_db(tmp_path_factory):
    feed_dir = tmp_path_factory.mktemp("feed") / "gtfs"
    sample_feed.build_feed(feed_dir)
    conn = gtfs.connect(":memory:")
    gtfs.load_feed(feed_dir, conn)
    return conn


def test_all_routes_present(sample_db):
    n = sample_db.execute("SELECT COUNT(*) AS n FROM routes").fetchone()["n"]
    assert n == len(sample_feed.ALL_ROUTES) == 10


def test_stop_times_reference_known_stops(sample_db):
    orphans = sample_db.execute(
        "SELECT COUNT(*) AS n FROM stop_times st "
        "LEFT JOIN stops s ON s.stop_id = st.stop_id WHERE s.stop_id IS NULL"
    ).fetchone()["n"]
    assert orphans == 0


def test_trips_reference_known_services(sample_db):
    orphans = sample_db.execute(
        "SELECT COUNT(*) AS n FROM trips t "
        "LEFT JOIN calendar c ON c.service_id = t.service_id "
        "WHERE c.service_id IS NULL"
    ).fetchone()["n"]
    assert orphans == 0


def test_stop_times_monotonic_within_trips(sample_db):
    bad = sample_db.execute(
        """
        SELECT COUNT(*) AS n FROM stop_times a
        JOIN stop_times b ON b.trip_id = a.trip_id
            AND b.stop_sequence = a.stop_sequence + 1
        WHERE b.arrival_secs < a.departure_secs
        """
    ).fetchone()["n"]
    assert bad == 0


def test_no_short_headway_at_block_boundaries(sample_db):
    """First-stop departures per route/direction never bunch below 5 minutes."""
    for route in sample_feed.ALL_ROUTES:
        for direction in (0, 1):
            departures = [
                row["departure_secs"]
                for row in sample_db.execute(
                    """
                    SELECT st.departure_secs FROM trips t
                    JOIN stop_times st ON st.trip_id = t.trip_id
                        AND st.stop_sequence = 1
                    WHERE t.route_id = ? AND t.direction_id = ?
                      AND t.service_id = 'WEEKDAY'
                    ORDER BY st.departure_secs
                    """,
                    (route.route_id, direction),
                )
            ]
            gaps = [b - a for a, b in zip(departures, departures[1:])]
            assert all(g >= 300 for g in gaps), (route.route_id, direction, min(gaps))


def test_holiday_swaps_to_sunday_service(sample_db):
    services = gtfs.service_ids_on(sample_db, date(2026, 7, 3))
    assert services == {"SUNDAY"}


def test_zip_output(tmp_path):
    feed_dir = tmp_path / "gtfs"
    zip_path = tmp_path / "gtfs.zip"
    sample_feed.build_feed(feed_dir, zip_path=zip_path)
    conn = gtfs.connect(":memory:")
    counts = gtfs.load_feed(zip_path, conn)
    assert counts["routes"] == 10
    assert counts["stop_times"] > 0
