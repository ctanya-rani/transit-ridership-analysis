"""Ridership data for the analytics pipeline.

GTFS describes service, not demand, so ridership comes from one of two
sources sharing the same ``ridership`` table:

* :func:`simulate` generates deterministic APC-style (automatic passenger
  counter) records — boardings, alightings and onboard load per trip stop —
  from the schedule itself. Demand follows route mode, stop attraction
  weights, time-of-day curves and day type, with seeded Poisson noise, and
  every trip's load profile is internally consistent (alightings never
  exceed the onboard load; everyone alights by the last stop).
* :func:`load_apc_csv` ingests real APC exports with columns
  ``service_date, trip_id, stop_id, stop_sequence, boardings, alightings``
  (``load`` optional; reconstructed from the running sum when absent).
"""

from __future__ import annotations

import csv
import math
import random
import sqlite3
from datetime import date
from pathlib import Path

from .gtfs import date_range, service_ids_on

# Relative demand level per GTFS route_type (0 light rail, 1 metro,
# 2 commuter rail, 3 bus), tuned so per-trip boardings land in a plausible
# band for each mode.
MODE_DEMAND = {0: 180.0, 1: 200.0, 2: 320.0, 3: 45.0}
DEFAULT_MODE_DEMAND = 60.0

# Hour-of-day boarding multipliers (index = hour % 24).
WEEKDAY_CURVE = [
    0.05, 0.02, 0.02, 0.05, 0.2, 0.5, 1.1, 1.6, 1.5, 1.0, 0.8, 0.85,
    0.9, 0.85, 0.9, 1.2, 1.6, 1.7, 1.2, 0.8, 0.6, 0.45, 0.3, 0.15,
]
WEEKEND_CURVE = [
    0.1, 0.05, 0.03, 0.03, 0.08, 0.2, 0.4, 0.6, 0.85, 1.1, 1.25, 1.3,
    1.3, 1.25, 1.2, 1.15, 1.1, 1.0, 0.9, 0.75, 0.6, 0.5, 0.4, 0.25,
]
WEEKEND_LEVEL = 0.55  # overall weekend demand vs weekday


def simulate(
    conn: sqlite3.Connection,
    start: date,
    days: int,
    seed: int = 42,
    replace: bool = True,
) -> int:
    """Generate simulated APC records for every trip in the date range.

    Returns the number of stop-level records written.
    """
    rng = random.Random(seed)
    trips_by_service = _trips_by_service(conn)
    stop_weights = _stop_weights(conn)
    route_demand = {
        row["route_id"]: MODE_DEMAND.get(row["route_type"], DEFAULT_MODE_DEMAND)
        for row in conn.execute("SELECT route_id, route_type FROM routes")
    }

    if replace:
        conn.execute("DELETE FROM ridership WHERE source = 'simulated'")

    written = 0
    insert_sql = (
        "INSERT OR REPLACE INTO ridership "
        "(service_date, trip_id, stop_id, stop_sequence, boardings, alightings, "
        "load, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'simulated')"
    )
    with conn:
        for day in date_range(start, days):
            weekend = day.weekday() >= 5
            active = service_ids_on(conn, day)
            for service_id in sorted(active):
                for trip in trips_by_service.get(service_id, ()):
                    rows = _simulate_trip(
                        trip, day, weekend, route_demand, stop_weights, rng
                    )
                    conn.executemany(insert_sql, rows)
                    written += len(rows)
    return written


def _simulate_trip(trip, day, weekend, route_demand, stop_weights, rng):
    trip_id, route_id, stop_times = trip
    curve = WEEKEND_CURVE if weekend else WEEKDAY_CURVE
    level = route_demand.get(route_id, DEFAULT_MODE_DEMAND)
    if weekend:
        level *= WEEKEND_LEVEL
    # Small day-to-day variation, deterministic per (trip, date).
    day_factor = 0.85 + 0.3 * _unit_hash(f"{trip_id}:{day.isoformat()}")

    n = len(stop_times)
    date_str = day.isoformat()
    boardings = [0] * n
    alightings = [0] * n
    for i, (stop_id, _seq, depart_secs) in enumerate(stop_times):
        if i == n - 1:
            break  # no boardings at the terminal
        hour = (depart_secs // 3600) % 24
        remaining_pull = sum(stop_weights.get(s, 1.0) for s, _, _ in stop_times[i + 1:])
        expected = (
            level
            * curve[hour]
            * day_factor
            * stop_weights.get(stop_id, 1.0)
            * min(1.0, remaining_pull / 3.0)
            / max(6.0, n * 0.75)
        )
        riders = _poisson(rng, expected)
        boardings[i] = riders
        # Assign each boarding an alighting stop further down the trip,
        # weighted by downstream stop attraction.
        weights = [stop_weights.get(s, 1.0) for s, _, _ in stop_times[i + 1:]]
        for _ in range(riders):
            j = i + 1 + _weighted_choice(rng, weights)
            alightings[j] += 1

    rows = []
    load = 0
    for i, (stop_id, seq, _depart) in enumerate(stop_times):
        load += boardings[i] - alightings[i]
        rows.append((date_str, trip_id, stop_id, seq, boardings[i], alightings[i], load))
    return rows


def load_apc_csv(conn: sqlite3.Connection, csv_path: str | Path, replace: bool = True) -> int:
    """Load real APC ridership records from a CSV export."""
    path = Path(csv_path)
    required = {"service_date", "trip_id", "stop_id", "stop_sequence",
                "boardings", "alightings"}
    written = 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"APC csv missing columns: {sorted(missing)}")
        with conn:
            if replace:
                conn.execute("DELETE FROM ridership WHERE source = 'apc'")
            load = 0
            last_trip_key = None
            for row in reader:
                trip_key = (row["service_date"], row["trip_id"])
                if trip_key != last_trip_key:
                    load = 0
                    last_trip_key = trip_key
                boardings = int(row["boardings"])
                alightings = int(row["alightings"])
                load = int(row["load"]) if row.get("load") else load + boardings - alightings
                conn.execute(
                    "INSERT OR REPLACE INTO ridership VALUES (?, ?, ?, ?, ?, ?, ?, 'apc')",
                    (row["service_date"], row["trip_id"], row["stop_id"],
                     int(row["stop_sequence"]), boardings, alightings, load),
                )
                written += 1
    return written


def _trips_by_service(conn: sqlite3.Connection):
    """Map service_id -> [(trip_id, route_id, [(stop_id, seq, depart_secs)...])]."""
    trips: dict[str, tuple[str, str, list]] = {}
    by_service: dict[str, list] = {}
    for row in conn.execute(
        "SELECT trip_id, route_id, service_id FROM trips ORDER BY trip_id"
    ):
        entry = (row["trip_id"], row["route_id"], [])
        trips[row["trip_id"]] = entry
        by_service.setdefault(row["service_id"], []).append(entry)
    for row in conn.execute(
        "SELECT trip_id, stop_id, stop_sequence, departure_secs FROM stop_times "
        "ORDER BY trip_id, stop_sequence"
    ):
        entry = trips.get(row["trip_id"])
        if entry is not None:
            entry[2].append(
                (row["stop_id"], row["stop_sequence"], row["departure_secs"] or 0)
            )
    return by_service


def _stop_weights(conn: sqlite3.Connection) -> dict[str, float]:
    """Attraction weight per stop: how many scheduled trips serve it.

    Hubs served by many trips (downtown stations, transit centers) both
    generate and attract more riders. Normalized so the median stop is 1.0.
    """
    counts = {
        row["stop_id"]: row["n"]
        for row in conn.execute(
            "SELECT stop_id, COUNT(*) AS n FROM stop_times GROUP BY stop_id"
        )
    }
    if not counts:
        return {}
    median = sorted(counts.values())[len(counts) // 2]
    return {
        stop_id: max(0.3, math.sqrt(n / max(median, 1)))
        for stop_id, n in counts.items()
    }


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:  # normal approximation for large lambda
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    threshold = math.exp(-lam)
    k, product = 0, rng.random()
    while product > threshold:
        k += 1
        product *= rng.random()
    return k


def _weighted_choice(rng: random.Random, weights: list[float]) -> int:
    total = sum(weights)
    if total <= 0:
        return rng.randrange(len(weights))
    pick = rng.random() * total
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if pick <= cumulative:
            return i
    return len(weights) - 1


def _unit_hash(text: str) -> float:
    """Deterministic pseudo-random float in [0, 1) from a string."""
    h = 2166136261
    for ch in text.encode():
        h = (h ^ ch) * 16777619 % (2**32)
    return h / 2**32
