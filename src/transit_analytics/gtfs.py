"""GTFS feed ingestion into SQLite.

Accepts a GTFS feed as either a ``.zip`` archive or a directory of ``.txt``
files and loads the core tables needed for service and ridership analytics:
agency, routes, stops, trips, stop_times, calendar and calendar_dates.

Times in ``stop_times`` may legally exceed 24:00:00 (trips running past
midnight belong to the previous service day), so they are stored as seconds
since noon-minus-12h ("GTFS seconds") in integer columns alongside the raw
strings.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator

CORE_FILES = {
    "agency.txt",
    "routes.txt",
    "stops.txt",
    "trips.txt",
    "stop_times.txt",
    "calendar.txt",
    "calendar_dates.txt",
}

# Files without which the feed can't produce any useful analytics.
REQUIRED_FILES = ("routes.txt", "stops.txt", "trips.txt", "stop_times.txt")
# At least one of calendar.txt / calendar_dates.txt must define service days.
CALENDAR_FILES = ("calendar.txt", "calendar_dates.txt")

REQUIRED_COLUMNS = {
    "routes.txt": ("route_id",),
    "stops.txt": ("stop_id",),
    "trips.txt": ("trip_id", "route_id", "service_id"),
    "stop_times.txt": ("trip_id", "stop_id", "stop_sequence"),
    "calendar.txt": ("service_id", "start_date", "end_date"),
    "calendar_dates.txt": ("service_id", "date", "exception_type"),
}


class GTFSValidationError(ValueError):
    """A GTFS feed is missing required files, columns, or rows."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS agency (
    agency_id TEXT PRIMARY KEY,
    agency_name TEXT NOT NULL,
    agency_url TEXT,
    agency_timezone TEXT
);
CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY,
    agency_id TEXT,
    route_short_name TEXT,
    route_long_name TEXT,
    route_type INTEGER,
    route_color TEXT
);
CREATE TABLE IF NOT EXISTS stops (
    stop_id TEXT PRIMARY KEY,
    stop_name TEXT NOT NULL,
    stop_lat REAL,
    stop_lon REAL,
    zone_id TEXT
);
CREATE TABLE IF NOT EXISTS trips (
    trip_id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    trip_headsign TEXT,
    direction_id INTEGER
);
CREATE TABLE IF NOT EXISTS stop_times (
    trip_id TEXT NOT NULL,
    stop_sequence INTEGER NOT NULL,
    stop_id TEXT NOT NULL,
    arrival_time TEXT,
    departure_time TEXT,
    arrival_secs INTEGER,
    departure_secs INTEGER,
    PRIMARY KEY (trip_id, stop_sequence)
);
CREATE TABLE IF NOT EXISTS calendar (
    service_id TEXT PRIMARY KEY,
    monday INTEGER, tuesday INTEGER, wednesday INTEGER, thursday INTEGER,
    friday INTEGER, saturday INTEGER, sunday INTEGER,
    start_date TEXT, end_date TEXT
);
CREATE TABLE IF NOT EXISTS calendar_dates (
    service_id TEXT NOT NULL,
    date TEXT NOT NULL,
    exception_type INTEGER NOT NULL,
    PRIMARY KEY (service_id, date)
);
CREATE TABLE IF NOT EXISTS ridership (
    service_date TEXT NOT NULL,
    trip_id TEXT NOT NULL,
    stop_id TEXT NOT NULL,
    stop_sequence INTEGER NOT NULL,
    boardings INTEGER NOT NULL,
    alightings INTEGER NOT NULL,
    load INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'simulated',
    PRIMARY KEY (service_date, trip_id, stop_sequence)
);
CREATE INDEX IF NOT EXISTS idx_stop_times_trip ON stop_times (trip_id);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON stop_times (stop_id);
CREATE INDEX IF NOT EXISTS idx_trips_route ON trips (route_id);
CREATE INDEX IF NOT EXISTS idx_trips_service ON trips (service_id);
CREATE INDEX IF NOT EXISTS idx_ridership_date ON ridership (service_date);
CREATE INDEX IF NOT EXISTS idx_ridership_trip ON ridership (trip_id);
CREATE INDEX IF NOT EXISTS idx_ridership_stop ON ridership (stop_id);
"""

WEEKDAY_COLUMNS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def parse_gtfs_time(value: str) -> int | None:
    """Parse a GTFS HH:MM:SS time (hours may exceed 23) into seconds."""
    value = (value or "").strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid GTFS time: {value!r}")
    hours, minutes, seconds = (int(p) for p in parts)
    if not (0 <= minutes < 60 and 0 <= seconds < 60 and hours >= 0):
        raise ValueError(f"invalid GTFS time: {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def format_gtfs_time(secs: int) -> str:
    return f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@dataclass
class FeedReader:
    """Reads .txt tables from a GTFS zip archive or directory."""

    source: Path

    def available_files(self) -> set[str]:
        if self.source.is_dir():
            return {p.name for p in self.source.glob("*.txt")}
        try:
            with zipfile.ZipFile(self.source) as zf:
                # Feeds are sometimes zipped with a wrapper folder; only keep
                # the basename so "gtfs/routes.txt" still counts as routes.txt.
                return {Path(n).name for n in zf.namelist() if n.endswith(".txt")}
        except zipfile.BadZipFile as exc:
            raise GTFSValidationError(
                f"{self.source.name} is not a valid .zip archive"
            ) from exc

    def header(self, name: str) -> list[str]:
        """Column names of the first row, or [] if the file is empty.

        Only meaningful for files already confirmed present via
        ``available_files()`` — ``open_table`` is a generator function, so
        for a missing file this simply yields nothing rather than raising.
        """
        try:
            first = next(iter(self.open_table(name)))
        except StopIteration:
            return []
        return list(first.keys())

    def open_table(self, name: str) -> Iterator[dict[str, str]] | None:
        if self.source.is_dir():
            path = self.source / name
            if not path.exists():
                return None
            with path.open(newline="", encoding="utf-8-sig") as fh:
                yield from csv.DictReader(fh)
        else:
            with zipfile.ZipFile(self.source) as zf:
                match = next(
                    (n for n in zf.namelist() if Path(n).name == name), None
                )
                if match is None:
                    return None
                with zf.open(match) as raw:
                    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                    yield from csv.DictReader(text)


def _rows(reader: FeedReader, name: str) -> Iterable[dict[str, str]]:
    table = reader.open_table(name)
    return table if table is not None else ()


def validate_feed(reader: FeedReader) -> None:
    """Raise GTFSValidationError with a specific, actionable message.

    Checks (in order, so the reader sees the most fundamental problem
    first): the archive is readable, every required file is present, at
    least one calendar source exists, and required columns are present in
    each required file.
    """
    available = reader.available_files()

    missing_required = [f for f in REQUIRED_FILES if f not in available]
    if missing_required:
        raise GTFSValidationError(
            "GTFS feed is missing required file(s): "
            + ", ".join(sorted(missing_required))
            + ". A valid feed needs routes.txt, stops.txt, trips.txt and "
            "stop_times.txt at minimum."
        )

    if not any(f in available for f in CALENDAR_FILES):
        raise GTFSValidationError(
            "GTFS feed has neither calendar.txt nor calendar_dates.txt, so "
            "no service days can be determined."
        )

    for filename in REQUIRED_FILES:
        header = set(reader.header(filename))
        missing_cols = [c for c in REQUIRED_COLUMNS[filename] if c not in header]
        if missing_cols:
            raise GTFSValidationError(
                f"{filename} is missing required column(s): "
                + ", ".join(missing_cols)
            )

    for filename in CALENDAR_FILES:
        if filename not in available:
            continue
        header = set(reader.header(filename))
        missing_cols = [c for c in REQUIRED_COLUMNS[filename] if c not in header]
        if missing_cols:
            raise GTFSValidationError(
                f"{filename} is missing required column(s): "
                + ", ".join(missing_cols)
            )


def load_feed(gtfs_path: str | Path, conn: sqlite3.Connection) -> dict[str, int]:
    """Load a GTFS feed into the database. Returns row counts per table.

    Raises ``GTFSValidationError`` (a ``ValueError``) with a specific,
    human-readable reason if the feed is missing required files/columns or
    a row is malformed, rather than silently loading partial data or
    surfacing a raw ``KeyError``/``zipfile`` traceback.
    """
    source = Path(gtfs_path)
    if not source.exists():
        raise FileNotFoundError(f"GTFS feed not found: {source}")
    reader = FeedReader(source)
    validate_feed(reader)
    counts: dict[str, int] = {}

    with conn:
        conn.execute("DELETE FROM agency")
        conn.execute("DELETE FROM routes")
        conn.execute("DELETE FROM stops")
        conn.execute("DELETE FROM trips")
        conn.execute("DELETE FROM stop_times")
        conn.execute("DELETE FROM calendar")
        conn.execute("DELETE FROM calendar_dates")

        counts["agency"] = _insert_many(
            conn,
            "INSERT INTO agency VALUES (?, ?, ?, ?)",
            (
                (
                    r.get("agency_id") or r.get("agency_name", ""),
                    r.get("agency_name", ""),
                    r.get("agency_url"),
                    r.get("agency_timezone"),
                )
                for r in _rows(reader, "agency.txt")
            ),
            table="agency.txt",
        )
        counts["routes"] = _insert_many(
            conn,
            "INSERT INTO routes VALUES (?, ?, ?, ?, ?, ?)",
            (
                (
                    r["route_id"],
                    r.get("agency_id"),
                    r.get("route_short_name", ""),
                    r.get("route_long_name", ""),
                    int(r["route_type"]) if r.get("route_type") else None,
                    r.get("route_color"),
                )
                for r in _rows(reader, "routes.txt")
            ),
            table="routes.txt",
        )
        counts["stops"] = _insert_many(
            conn,
            "INSERT INTO stops VALUES (?, ?, ?, ?, ?)",
            (
                (
                    r["stop_id"],
                    r.get("stop_name", ""),
                    float(r["stop_lat"]) if r.get("stop_lat") else None,
                    float(r["stop_lon"]) if r.get("stop_lon") else None,
                    r.get("zone_id"),
                )
                for r in _rows(reader, "stops.txt")
            ),
            table="stops.txt",
        )
        counts["trips"] = _insert_many(
            conn,
            "INSERT INTO trips VALUES (?, ?, ?, ?, ?)",
            (
                (
                    r["trip_id"],
                    r["route_id"],
                    r["service_id"],
                    r.get("trip_headsign"),
                    int(r["direction_id"]) if r.get("direction_id") else 0,
                )
                for r in _rows(reader, "trips.txt")
            ),
            table="trips.txt",
        )
        counts["stop_times"] = _insert_many(
            conn,
            "INSERT INTO stop_times VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    r["trip_id"],
                    int(r["stop_sequence"]),
                    r["stop_id"],
                    r.get("arrival_time"),
                    r.get("departure_time"),
                    parse_gtfs_time(r.get("arrival_time", "")),
                    parse_gtfs_time(r.get("departure_time", "")),
                )
                for r in _rows(reader, "stop_times.txt")
            ),
            table="stop_times.txt",
        )
        counts["calendar"] = _insert_many(
            conn,
            "INSERT INTO calendar VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    r["service_id"],
                    *(int(r.get(day, 0) or 0) for day in WEEKDAY_COLUMNS),
                    r.get("start_date", ""),
                    r.get("end_date", ""),
                )
                for r in _rows(reader, "calendar.txt")
            ),
            table="calendar.txt",
        )
        counts["calendar_dates"] = _insert_many(
            conn,
            "INSERT INTO calendar_dates VALUES (?, ?, ?)",
            (
                (r["service_id"], r["date"], int(r["exception_type"]))
                for r in _rows(reader, "calendar_dates.txt")
            ),
            table="calendar_dates.txt",
        )
    return counts


def _insert_many(
    conn: sqlite3.Connection, sql: str, rows: Iterable[tuple], table: str = "?"
) -> int:
    try:
        cursor = conn.executemany(sql, rows)
    except (KeyError, ValueError, TypeError) as exc:
        raise GTFSValidationError(
            f"malformed row in {table}: {exc}"
        ) from exc
    return cursor.rowcount if cursor.rowcount >= 0 else 0


def service_ids_on(conn: sqlite3.Connection, day: date) -> set[str]:
    """Resolve which service_ids run on a calendar date (calendar + exceptions)."""
    yyyymmdd = day.strftime("%Y%m%d")
    weekday_col = WEEKDAY_COLUMNS[day.weekday()]
    active = {
        row["service_id"]
        for row in conn.execute(
            f"SELECT service_id FROM calendar "
            f"WHERE {weekday_col} = 1 AND start_date <= ? AND end_date >= ?",
            (yyyymmdd, yyyymmdd),
        )
    }
    for row in conn.execute(
        "SELECT service_id, exception_type FROM calendar_dates WHERE date = ?",
        (yyyymmdd,),
    ):
        if row["exception_type"] == 1:
            active.add(row["service_id"])
        elif row["exception_type"] == 2:
            active.discard(row["service_id"])
    return active


def date_range(start: date, days: int) -> Iterator[date]:
    for offset in range(days):
        yield start + timedelta(days=offset)


def feed_date_bounds(conn: sqlite3.Connection) -> tuple[date, date] | None:
    """Overall [earliest, latest] service date across calendar + calendar_dates.

    Returns None if the feed defines no dates at all (shouldn't happen for a
    feed that passed ``validate_feed``, but callers may hand in an empty db).
    """
    bounds: list[tuple[str, str]] = []
    row = conn.execute(
        "SELECT MIN(start_date) AS lo, MAX(end_date) AS hi FROM calendar"
    ).fetchone()
    if row and row["lo"] and row["hi"]:
        bounds.append((row["lo"], row["hi"]))
    row = conn.execute(
        "SELECT MIN(date) AS lo, MAX(date) AS hi FROM calendar_dates"
    ).fetchone()
    if row and row["lo"] and row["hi"]:
        bounds.append((row["lo"], row["hi"]))
    if not bounds:
        return None
    lo = min(b[0] for b in bounds)
    hi = max(b[1] for b in bounds)
    try:
        return (
            datetime.strptime(lo, "%Y%m%d").date(),
            datetime.strptime(hi, "%Y%m%d").date(),
        )
    except ValueError:
        return None


def pick_simulation_window(
    conn: sqlite3.Connection, preferred_days: int = 28
) -> tuple[date, int]:
    """Pick a representative [start, days] window inside the feed's validity.

    Prefers starting on a Monday (so a short window still captures a
    weekday/weekend mix) and always stays within the feed's own calendar
    bounds, so simulated ridership never silently comes back empty because
    the window fell outside every service_id's date range.
    """
    bounds = feed_date_bounds(conn)
    if bounds is None:
        return date.today(), preferred_days
    lo, hi = bounds
    span_days = (hi - lo).days + 1
    days = min(preferred_days, max(span_days, 1))

    start = lo
    while start.weekday() != 0 and (start - lo).days < 7:
        candidate = start + timedelta(days=1)
        if candidate + timedelta(days=days - 1) > hi:
            break
        start = candidate
    if start + timedelta(days=days - 1) > hi:
        start = max(lo, hi - timedelta(days=days - 1))
    return start, days
