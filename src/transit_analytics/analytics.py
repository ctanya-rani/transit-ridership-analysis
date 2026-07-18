"""Analytics queries over the GTFS + ridership database.

All functions take an open SQLite connection (see ``gtfs.connect``) and
return plain dicts/lists so the CLI, dashboard and tests can share them.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime


def _weekend(date_str: str) -> bool:
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5


def system_summary(conn: sqlite3.Connection) -> dict:
    """Headline KPIs across the loaded ridership window."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT service_date) AS days, "
        "       COUNT(DISTINCT trip_id) AS trips, "
        "       SUM(boardings) AS boardings "
        "FROM ridership"
    ).fetchone()
    daily = daily_boardings(conn)
    weekdays = [d["boardings"] for d in daily if not d["is_weekend"]]
    weekends = [d["boardings"] for d in daily if d["is_weekend"]]
    routes = boardings_by_route(conn)
    stops = top_stops(conn, limit=1)
    return {
        "days": row["days"] or 0,
        "total_boardings": row["boardings"] or 0,
        "avg_weekday_boardings": round(sum(weekdays) / len(weekdays)) if weekdays else 0,
        "avg_weekend_boardings": round(sum(weekends) / len(weekends)) if weekends else 0,
        "busiest_route": routes[0] if routes else None,
        "busiest_stop": stops[0] if stops else None,
        "n_routes": conn.execute("SELECT COUNT(*) AS n FROM routes").fetchone()["n"],
        "n_stops": conn.execute("SELECT COUNT(*) AS n FROM stops").fetchone()["n"],
    }


def daily_boardings(conn: sqlite3.Connection) -> list[dict]:
    """Total boardings per service date, flagged weekday/weekend."""
    return [
        {
            "date": row["service_date"],
            "boardings": row["boardings"],
            "is_weekend": _weekend(row["service_date"]),
        }
        for row in conn.execute(
            "SELECT service_date, SUM(boardings) AS boardings "
            "FROM ridership GROUP BY service_date ORDER BY service_date"
        )
    ]


def boardings_by_route(conn: sqlite3.Connection) -> list[dict]:
    """Average daily boardings and productivity per route, busiest first."""
    n_days = conn.execute(
        "SELECT COUNT(DISTINCT service_date) AS n FROM ridership"
    ).fetchone()["n"]
    if not n_days:
        return []
    rows = conn.execute(
        """
        SELECT r.route_id, r.route_short_name, r.route_long_name, r.route_type,
               r.route_color,
               SUM(rd.boardings) AS total_boardings,
               COUNT(DISTINCT rd.service_date || '|' || rd.trip_id) AS trips_run
        FROM ridership rd
        JOIN trips t ON t.trip_id = rd.trip_id
        JOIN routes r ON r.route_id = t.route_id
        GROUP BY r.route_id
        ORDER BY total_boardings DESC
        """
    ).fetchall()
    revenue_hours = _revenue_hours_by_route(conn)
    result = []
    for row in rows:
        avg_daily = row["total_boardings"] / n_days
        trips_per_day = row["trips_run"] / n_days
        hours = revenue_hours.get(row["route_id"], 0.0)
        result.append(
            {
                "route_id": row["route_id"],
                "short_name": row["route_short_name"],
                "long_name": row["route_long_name"],
                "route_type": row["route_type"],
                "color": row["route_color"],
                "avg_daily_boardings": round(avg_daily),
                "trips_per_day": round(trips_per_day, 1),
                "boardings_per_trip": round(
                    row["total_boardings"] / row["trips_run"], 1
                ) if row["trips_run"] else 0.0,
                "boardings_per_revenue_hour": round(avg_daily / hours, 1) if hours else None,
            }
        )
    return result


def _revenue_hours_by_route(conn: sqlite3.Connection) -> dict[str, float]:
    """Average daily scheduled revenue hours per route over the ridership window."""
    rows = conn.execute(
        """
        WITH trip_span AS (
            SELECT trip_id,
                   (MAX(arrival_secs) - MIN(departure_secs)) / 3600.0 AS hours
            FROM stop_times GROUP BY trip_id
        )
        SELECT t.route_id, SUM(ts.hours) AS hours,
               COUNT(DISTINCT rd.service_date) AS n_days
        FROM ridership rd
        JOIN trips t ON t.trip_id = rd.trip_id
        JOIN trip_span ts ON ts.trip_id = rd.trip_id
        WHERE rd.stop_sequence = 1
        GROUP BY t.route_id
        """
    ).fetchall()
    return {
        row["route_id"]: row["hours"] / row["n_days"]
        for row in rows
        if row["n_days"]
    }


def top_stops(conn: sqlite3.Connection, limit: int = 15) -> list[dict]:
    """Busiest stops by average daily boardings."""
    n_days = conn.execute(
        "SELECT COUNT(DISTINCT service_date) AS n FROM ridership"
    ).fetchone()["n"]
    if not n_days:
        return []
    return [
        {
            "stop_id": row["stop_id"],
            "stop_name": row["stop_name"],
            "avg_daily_boardings": round(row["boardings"] / n_days),
            "avg_daily_alightings": round(row["alightings"] / n_days),
        }
        for row in conn.execute(
            """
            SELECT s.stop_id, s.stop_name,
                   SUM(rd.boardings) AS boardings, SUM(rd.alightings) AS alightings
            FROM ridership rd JOIN stops s ON s.stop_id = rd.stop_id
            GROUP BY s.stop_id ORDER BY boardings DESC LIMIT ?
            """,
            (limit,),
        )
    ]


def hourly_profile(conn: sqlite3.Connection) -> list[dict]:
    """Average boardings per hour of day, split weekday vs weekend."""
    weekday_totals = [0] * 24
    weekend_totals = [0] * 24
    weekday_days: set[str] = set()
    weekend_days: set[str] = set()
    for row in conn.execute(
        """
        SELECT rd.service_date, (st.departure_secs / 3600) % 24 AS hour,
               SUM(rd.boardings) AS boardings
        FROM ridership rd
        JOIN stop_times st
          ON st.trip_id = rd.trip_id AND st.stop_sequence = rd.stop_sequence
        WHERE st.departure_secs IS NOT NULL
        GROUP BY rd.service_date, hour
        """
    ):
        hour = int(row["hour"])
        if _weekend(row["service_date"]):
            weekend_totals[hour] += row["boardings"]
            weekend_days.add(row["service_date"])
        else:
            weekday_totals[hour] += row["boardings"]
            weekday_days.add(row["service_date"])
    n_wd, n_we = max(len(weekday_days), 1), max(len(weekend_days), 1)
    return [
        {
            "hour": h,
            "weekday": round(weekday_totals[h] / n_wd),
            "weekend": round(weekend_totals[h] / n_we),
        }
        for h in range(24)
    ]


def route_headways(conn: sqlite3.Connection) -> list[dict]:
    """Scheduled weekday headway stats per route (direction 0, first stop)."""
    result = []
    for route in conn.execute(
        "SELECT route_id, route_short_name FROM routes ORDER BY route_id"
    ):
        departures = [
            row["departure_secs"]
            for row in conn.execute(
                """
                SELECT st.departure_secs FROM trips t
                JOIN stop_times st ON st.trip_id = t.trip_id AND st.stop_sequence = 1
                JOIN calendar c ON c.service_id = t.service_id
                WHERE t.route_id = ? AND t.direction_id = 0 AND c.monday = 1
                  AND st.departure_secs IS NOT NULL
                ORDER BY st.departure_secs
                """,
                (route["route_id"],),
            )
        ]
        if len(departures) < 2:
            continue
        gaps = [b - a for a, b in zip(departures, departures[1:]) if b > a]
        if not gaps:
            continue
        result.append(
            {
                "route_id": route["route_id"],
                "short_name": route["route_short_name"],
                "trips_per_weekday": len(departures),
                "min_headway_min": round(min(gaps) / 60),
                "median_headway_min": round(sorted(gaps)[len(gaps) // 2] / 60),
                "span": _span_str(departures[0], departures[-1]),
            }
        )
    return result


def _span_str(first_secs: int, last_secs: int) -> str:
    def clock(secs: int) -> str:
        return f"{secs // 3600 % 24:02d}:{secs % 3600 // 60:02d}"

    return f"{clock(first_secs)}–{clock(last_secs)}"


def route_load_profile(conn: sqlite3.Connection, route_id: str,
                       direction_id: int = 0) -> list[dict]:
    """Average onboard load by stop for a route direction (weekdays)."""
    rows = conn.execute(
        """
        SELECT rd.stop_sequence, s.stop_name,
               AVG(rd.load) AS avg_load, AVG(rd.boardings) AS avg_boardings
        FROM ridership rd
        JOIN trips t ON t.trip_id = rd.trip_id
        JOIN stops s ON s.stop_id = rd.stop_id
        WHERE t.route_id = ? AND t.direction_id = ?
        GROUP BY rd.stop_sequence, s.stop_name
        ORDER BY rd.stop_sequence
        """,
        (route_id, direction_id),
    ).fetchall()
    return [
        {
            "stop_sequence": row["stop_sequence"],
            "stop_name": row["stop_name"],
            "avg_load": round(row["avg_load"], 1),
            "avg_boardings": round(row["avg_boardings"], 1),
        }
        for row in rows
    ]
