"""Generate a sample GTFS feed modeled on Seattle's Sound Transit network.

The station lists, route names and rough headways mirror the real network
(Link 1 Line and 2 Line, Sounder N and S Lines, and a handful of ST Express
coach routes), but every schedule here is synthetic and generated
deterministically — this is demo data for exercising the analytics pipeline,
not an official Sound Transit feed. Real feeds ingest through the exact same
``load_feed`` path.
"""

from __future__ import annotations

import csv
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .gtfs import format_gtfs_time

FEED_START = "20260101"
FEED_END = "20261231"

# route_type: 0 tram/light rail, 2 rail, 3 bus
ROUTE_TYPE_LIGHT_RAIL = 0
ROUTE_TYPE_RAIL = 2
ROUTE_TYPE_BUS = 3


@dataclass
class RouteSpec:
    route_id: str
    short_name: str
    long_name: str
    route_type: int
    color: str
    # (stop_id, stop_name, lat, lon, minutes from previous stop)
    stops: list[tuple[str, str, float, float, int]]
    # service_id -> list of (first_departure_secs, last_departure_secs, headway_secs)
    frequency_blocks: dict[str, list[tuple[int, int, int]]] = field(default_factory=dict)
    dwell_secs: int = 30


def _h(hours: float) -> int:
    return int(hours * 3600)


LINK_1_LINE = RouteSpec(
    route_id="100479",
    short_name="1 Line",
    long_name="Lynnwood City Center - Angle Lake",
    route_type=ROUTE_TYPE_LIGHT_RAIL,
    color="00A651",
    stops=[
        ("LCC", "Lynnwood City Center", 47.8155, -122.2967, 0),
        ("MTS", "Mountlake Terrace", 47.7852, -122.3149, 4),
        ("S185", "Shoreline North/185th", 47.7599, -122.3122, 3),
        ("S148", "Shoreline South/148th", 47.7360, -122.3126, 3),
        ("NGT", "Northgate", 47.7031, -122.3282, 3),
        ("RVT", "Roosevelt", 47.6760, -122.3167, 3),
        ("UDS", "U District", 47.6606, -122.3140, 2),
        ("UWS", "University of Washington", 47.6498, -122.3037, 2),
        ("CHS", "Capitol Hill", 47.6192, -122.3202, 4),
        ("WLK", "Westlake", 47.6114, -122.3373, 3),
        ("SYM", "Symphony", 47.6076, -122.3355, 1),
        ("PSQ", "Pioneer Square", 47.6031, -122.3318, 2),
        ("IDS", "Int'l District/Chinatown", 47.5983, -122.3280, 2),
        ("STD", "Stadium", 47.5911, -122.3277, 2),
        ("SODO", "SODO", 47.5810, -122.3273, 2),
        ("BHS", "Beacon Hill", 47.5791, -122.3117, 3),
        ("MBS", "Mount Baker", 47.5764, -122.2977, 2),
        ("CCS", "Columbia City", 47.5599, -122.2926, 3),
        ("OTH", "Othello", 47.5379, -122.2818, 3),
        ("RBS", "Rainier Beach", 47.5224, -122.2794, 2),
        ("TIB", "Tukwila Int'l Blvd", 47.4642, -122.2880, 6),
        ("SEA", "SeaTac/Airport", 47.4451, -122.2971, 3),
        ("ALS", "Angle Lake", 47.4224, -122.2975, 3),
    ],
    frequency_blocks={
        "WEEKDAY": [
            (_h(5.0), _h(6.5), 600),
            (_h(6.5), _h(9.5), 480),
            (_h(9.5), _h(15.0), 600),
            (_h(15.0), _h(18.5), 480),
            (_h(18.5), _h(22.0), 600),
            (_h(22.0), _h(25.0), 900),
        ],
        "SATURDAY": [(_h(5.5), _h(22.0), 600), (_h(22.0), _h(25.0), 900)],
        "SUNDAY": [(_h(6.0), _h(22.0), 720), (_h(22.0), _h(24.5), 900)],
    },
)

LINK_2_LINE = RouteSpec(
    route_id="2LINE",
    short_name="2 Line",
    long_name="Downtown Redmond - South Bellevue",
    route_type=ROUTE_TYPE_LIGHT_RAIL,
    color="0077C0",
    stops=[
        ("DRS", "Downtown Redmond", 47.6740, -122.1215, 0),
        ("MVS", "Marymoor Village", 47.6664, -122.1102, 3),
        ("RTS", "Redmond Technology", 47.6444, -122.1338, 4),
        ("OVS", "Overlake Village", 47.6353, -122.1379, 2),
        ("BRS", "Bel-Red", 47.6224, -122.1450, 3),
        ("SDS", "Spring District", 47.6222, -122.1780, 3),
        ("WBS", "Wilburton", 47.6178, -122.1836, 2),
        ("BDS", "Bellevue Downtown", 47.6157, -122.1935, 2),
        ("EMS", "East Main", 47.6082, -122.1922, 2),
        ("SBS", "South Bellevue", 47.5875, -122.1902, 3),
    ],
    frequency_blocks={
        "WEEKDAY": [(_h(5.5), _h(9.5), 600), (_h(9.5), _h(15.0), 720),
                    (_h(15.0), _h(18.5), 600), (_h(18.5), _h(21.5), 720)],
        "SATURDAY": [(_h(6.5), _h(21.5), 720)],
        "SUNDAY": [(_h(7.0), _h(21.0), 900)],
    },
)

SOUNDER_N = RouteSpec(
    route_id="SNDR_N",
    short_name="N Line",
    long_name="Everett - Seattle",
    route_type=ROUTE_TYPE_RAIL,
    color="8CC63E",
    stops=[
        ("EVR", "Everett Station", 47.9754, -122.1974, 0),
        ("MUK", "Mukilteo Station", 47.9491, -122.3050, 12),
        ("EDM", "Edmonds Station", 47.8110, -122.3849, 13),
        ("KSS", "King Street Station", 47.5990, -122.3300, 34),
    ],
    frequency_blocks={
        # Peak-direction commuter service only.
        "WEEKDAY": [(_h(5.75), _h(7.25), 1800), (_h(16.1), _h(17.6), 1800)],
    },
    dwell_secs=60,
)

SOUNDER_S = RouteSpec(
    route_id="SNDR_S",
    short_name="S Line",
    long_name="Lakewood - Seattle",
    route_type=ROUTE_TYPE_RAIL,
    color="8CC63E",
    stops=[
        ("LKW", "Lakewood Station", 47.1543, -122.4966, 0),
        ("STA", "South Tacoma", 47.2038, -122.4864, 6),
        ("TAC", "Tacoma Dome Station", 47.2399, -122.4270, 8),
        ("PUY", "Puyallup Station", 47.1935, -122.2954, 12),
        ("SUM", "Sumner Station", 47.2036, -122.2429, 5),
        ("AUB", "Auburn Station", 47.3064, -122.2320, 9),
        ("KNT", "Kent Station", 47.3846, -122.2337, 7),
        ("TUK", "Tukwila Station", 47.4610, -122.2427, 7),
        ("KSS", "King Street Station", 47.5990, -122.3300, 12),
    ],
    frequency_blocks={
        "WEEKDAY": [(_h(4.6), _h(8.0), 1200), (_h(15.2), _h(18.6), 1200)],
    },
    dwell_secs=60,
)


def _bus(route_id: str, short: str, long_name: str, stops, weekday_peak_headway: int,
         weekday_base_headway: int, span=(5.5, 23.0), weekend: bool = True) -> RouteSpec:
    blocks = {
        "WEEKDAY": [
            (_h(span[0]), _h(6.5), weekday_base_headway),
            (_h(6.5), _h(9.0), weekday_peak_headway),
            (_h(9.0), _h(15.5), weekday_base_headway),
            (_h(15.5), _h(18.5), weekday_peak_headway),
            (_h(18.5), _h(span[1]), weekday_base_headway),
        ],
    }
    if weekend:
        blocks["SATURDAY"] = [(_h(span[0] + 1), _h(span[1] - 1), weekday_base_headway)]
        blocks["SUNDAY"] = [(_h(span[0] + 1.5), _h(span[1] - 1.5), weekday_base_headway + 600)]
    return RouteSpec(route_id, short, long_name, ROUTE_TYPE_BUS, "3F6BB6", stops, blocks)


ST_EXPRESS = [
    _bus("510", "510", "Everett - Seattle", [
        ("EVR", "Everett Station", 47.9754, -122.1974, 0),
        ("SEW", "South Everett Freeway Station", 47.9243, -122.2069, 8),
        ("ASH", "Ash Way Park & Ride", 47.8631, -122.2534, 7),
        ("LTC", "Lynnwood City Center", 47.8155, -122.2967, 6),
        ("DTS", "Downtown Seattle (5th & Pine)", 47.6119, -122.3372, 24),
    ], 900, 1800),
    _bus("545", "545", "Redmond - Seattle", [
        ("RTC", "Redmond Transit Center", 47.6786, -122.1263, 0),
        ("OTC", "Overlake Transit Center", 47.6444, -122.1338, 8),
        ("YRW", "Yarrow Point Freeway Station", 47.6432, -122.2180, 9),
        ("MTL", "Montlake Freeway Station", 47.6444, -122.3037, 6),
        ("DTS", "Downtown Seattle (4th & Pike)", 47.6096, -122.3372, 12),
    ], 600, 1200),
    _bus("550", "550", "Bellevue - Seattle", [
        ("BTC", "Bellevue Transit Center", 47.6154, -122.1953, 0),
        ("SBP", "South Bellevue Park & Ride", 47.5875, -122.1902, 8),
        ("MIP", "Mercer Island Park & Ride", 47.5800, -122.2280, 6),
        ("DTS", "Downtown Seattle (2nd & University)", 47.6070, -122.3350, 14),
    ], 600, 900),
    _bus("554", "554", "Issaquah - Seattle", [
        ("IHP", "Issaquah Highlands Park & Ride", 47.5442, -122.0195, 0),
        ("ITC", "Issaquah Transit Center", 47.5301, -122.0326, 5),
        ("EGP", "Eastgate Park & Ride", 47.5806, -122.1520, 9),
        ("MIP", "Mercer Island Park & Ride", 47.5800, -122.2280, 7),
        ("DTS", "Downtown Seattle (2nd & University)", 47.6070, -122.3350, 14),
    ], 900, 1800),
    _bus("590", "590", "Tacoma - Seattle", [
        ("TAC", "Tacoma Dome Station", 47.2399, -122.4270, 0),
        ("DTT", "Downtown Tacoma (10th & Commerce)", 47.2529, -122.4399, 6),
        ("SODO", "SODO Busway", 47.5810, -122.3273, 38),
        ("DTS", "Downtown Seattle (4th & Jackson)", 47.5990, -122.3287, 6),
    ], 600, 1800, weekend=False),
    _bus("594", "594", "Lakewood - Seattle", [
        ("LTC2", "Lakewood Towne Center", 47.1620, -122.5060, 0),
        ("SRP", "SR 512 Park & Ride", 47.1710, -122.4390, 8),
        ("TAC", "Tacoma Dome Station", 47.2399, -122.4270, 12),
        ("SODO", "SODO Busway", 47.5810, -122.3273, 38),
        ("DTS", "Downtown Seattle (4th & Jackson)", 47.5990, -122.3287, 6),
    ], 900, 1800),
]

ALL_ROUTES: list[RouteSpec] = [LINK_1_LINE, LINK_2_LINE, SOUNDER_N, SOUNDER_S, *ST_EXPRESS]


def build_feed(out_dir: str | Path, zip_path: str | Path | None = None) -> Path:
    """Write the sample GTFS feed as .txt files (and optionally a .zip)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    _write(out / "agency.txt",
           ["agency_id", "agency_name", "agency_url", "agency_timezone"],
           [["ST", "Sample Sound Transit (synthetic demo feed)",
             "https://example.org/sample-st", "America/Los_Angeles"]])

    _write(out / "routes.txt",
           ["route_id", "agency_id", "route_short_name", "route_long_name",
            "route_type", "route_color"],
           [[r.route_id, "ST", r.short_name, r.long_name, r.route_type, r.color]
            for r in ALL_ROUTES])

    seen: dict[str, list] = {}
    for route in ALL_ROUTES:
        for stop_id, name, lat, lon, _ in route.stops:
            seen.setdefault(stop_id, [stop_id, name, lat, lon])
    _write(out / "stops.txt",
           ["stop_id", "stop_name", "stop_lat", "stop_lon"],
           sorted(seen.values()))

    _write(out / "calendar.txt",
           ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday", "start_date", "end_date"],
           [["WEEKDAY", 1, 1, 1, 1, 1, 0, 0, FEED_START, FEED_END],
            ["SATURDAY", 0, 0, 0, 0, 0, 1, 0, FEED_START, FEED_END],
            ["SUNDAY", 0, 0, 0, 0, 0, 0, 1, FEED_START, FEED_END]])

    # Independence Day 2026 (a Saturday-observed holiday week): run Sunday
    # service on the Friday holiday instead of weekday service.
    _write(out / "calendar_dates.txt",
           ["service_id", "date", "exception_type"],
           [["WEEKDAY", "20260703", 2], ["SUNDAY", "20260703", 1]])

    trips_rows: list[list] = []
    stop_times_rows: list[list] = []
    for route in ALL_ROUTES:
        _build_route_trips(route, trips_rows, stop_times_rows)

    _write(out / "trips.txt",
           ["trip_id", "route_id", "service_id", "trip_headsign", "direction_id"],
           trips_rows)
    _write(out / "stop_times.txt",
           ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
           stop_times_rows)

    if zip_path is not None:
        zip_out = Path(zip_path)
        zip_out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
            for txt in sorted(out.glob("*.txt")):
                zf.write(txt, txt.name)
    return out


def _build_route_trips(route: RouteSpec, trips_rows: list, stop_times_rows: list) -> None:
    for direction_id in (0, 1):
        stops = route.stops if direction_id == 0 else _reverse_stops(route.stops)
        headsign = stops[-1][1]
        for service_id, blocks in route.frequency_blocks.items():
            trip_num = 0
            prev_depart: int | None = None
            for first, last, headway in blocks:
                depart = first
                # Offset direction 1 by half a headway so meets aren't in lockstep.
                if direction_id == 1:
                    depart += headway // 2
                # Don't let a new frequency block create a short gap against
                # the previous block's final departure.
                if prev_depart is not None:
                    depart = max(depart, prev_depart + headway)
                while depart <= last:
                    trip_num += 1
                    trip_id = f"{route.route_id}-{service_id[:3]}-{direction_id}-{trip_num:03d}"
                    trips_rows.append(
                        [trip_id, route.route_id, service_id, headsign, direction_id]
                    )
                    _build_stop_times(trip_id, stops, depart, route.dwell_secs,
                                      stop_times_rows)
                    prev_depart = depart
                    depart += headway


def _build_stop_times(trip_id: str, stops, start_secs: int, dwell: int,
                      out_rows: list) -> None:
    clock = start_secs
    for seq, (stop_id, _name, _lat, _lon, run_minutes) in enumerate(stops, start=1):
        clock += run_minutes * 60
        arrival = clock
        departure = clock if seq == len(stops) else clock + (dwell if seq > 1 else 0)
        out_rows.append([trip_id, format_gtfs_time(arrival), format_gtfs_time(departure),
                         stop_id, seq])
        clock = departure


def _reverse_stops(stops):
    """Reverse a stop list, shifting the leg run-times to match the new order."""
    reversed_stops = []
    run_times = [minutes for _, _, _, _, minutes in stops[1:]] + [0]
    for (stop_id, name, lat, lon, _), minutes in zip(reversed(stops), reversed(run_times)):
        reversed_stops.append((stop_id, name, lat, lon, minutes))
    return reversed_stops


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
