# Transit Ridership Analytics

Ridership analytics on open [GTFS](https://gtfs.org/) data — pure Python,
zero runtime dependencies, SQLite-backed, with a terminal report and a
self-contained HTML dashboard (light/dark, interactive tooltips, no CDN).

Ships with a synthetic sample feed **modeled on Seattle's Sound Transit
network** (Link 1 Line and 2 Line, Sounder N/S Lines, six ST Express
routes), so the whole pipeline runs offline out of the box. Any real GTFS
feed — Sound Transit, Amsterdam GVB via [ovapi.nl](http://gtfs.ovapi.nl/),
or any other agency — ingests through the same path.

## Quick start

### Local

```bash
pip install -e .
transit-analytics demo          # full pipeline into ./demo/
open demo/dashboard.html
```

The demo builds the sample feed, ingests it into SQLite, simulates 28 days
of APC-style ridership, prints the analytics report, and writes the
dashboard.

### Live web app

Deploy for free to Vercel + Railway in ~5 minutes: [**DEPLOYMENT.md**](DEPLOYMENT.md)

Once live, you get a shareable link to:
- View the demo dataset instantly
- Upload any GTFS feed (zip file) and get a dashboard

## The pipeline, step by step

```bash
# 1. Get a GTFS feed. Either generate the bundled sample…
transit-analytics build-sample --out data/gtfs_sample

#    …or download a real one, e.g.
#    Sound Transit: https://www.soundtransit.org/GTFS-rail/40_gtfs.zip
#    Amsterdam GVB: http://gtfs.ovapi.nl/gvb/gtfs-kv1cap.zip

# 2. Ingest it (zip or directory) into SQLite
transit-analytics ingest data/gtfs_sample --db transit.db

# 3. Add ridership — simulated, or real APC counts
transit-analytics simulate --db transit.db --start 2026-03-02 --days 28 --seed 42
transit-analytics load-apc counts.csv --db transit.db   # alternative: real data

# 4. Analyze
transit-analytics report --db transit.db
transit-analytics dashboard --db transit.db --out dashboard.html
```

## What you get

**Terminal report** (`report`) and **dashboard** (`dashboard`) cover:

- Headline KPIs — total boardings, average weekday vs weekend boardings,
  busiest route and stop, network size
- Daily boardings time series (weekend dips and holiday exceptions visible)
- Boardings by hour of day, weekday vs weekend profiles
- Route league table — boardings/day, trips/day, boardings/trip,
  boardings per revenue hour
- Busiest stops by boardings and alightings
- Scheduled weekday headways per route (trips, min/median headway, span)
- Route load profiles by stop (`analytics.route_load_profile`)

## About the ridership data

GTFS describes *service*, not *demand* — no open GTFS feed contains
ridership. This project therefore separates the two:

- **`simulate`** generates deterministic, APC-shaped records (boardings,
  alightings, onboard load per trip-stop) from the schedule itself: demand
  scales with route mode, stop attraction (how much service a stop sees),
  peak/off-peak curves, and day type, with seeded Poisson noise. Loads are
  internally consistent — nobody alights who isn't aboard, and every trip
  ends empty. Simulated data is labeled `source='simulated'` and flagged on
  the dashboard.
- **`load-apc`** ingests real automatic-passenger-counter exports
  (`service_date, trip_id, stop_id, stop_sequence, boardings, alightings[,load]`)
  into the same table with `source='apc'`, so the identical analytics run
  on real counts.

The sample feed's station lists, route names, and rough headways mirror
the real Sound Transit network, but all schedules and numbers are
synthetic demo data, not official statistics.

## Project layout

```
src/transit_analytics/
  gtfs.py         GTFS zip/directory → SQLite (times past 24:00 handled)
  sample_feed.py  synthetic Sound Transit-modeled feed generator
  ridership.py    APC simulator + real-APC CSV loader
  analytics.py    metric queries (shared by CLI, dashboard, tests)
  charts.py       inline-SVG chart builders (line, bar, stat tiles)
  dashboard.py    single-file HTML dashboard, light/dark, tooltips
  cli.py          transit-analytics entry point
tests/            pytest suite (42 tests)
web/              Next.js frontend (Vercel-ready)
api/              FastAPI backend (Railway/Fly.io-ready)
```

## Development

```bash
pip install -e . pytest
python -m pytest
```
