"""FastAPI backend for transit-analytics web app.

Two endpoints do the real work:

- ``GET /api/demo``    returns the pre-built demo dashboard (generated once,
  on process startup, from the bundled Sound Transit-modeled sample feed).
- ``POST /api/upload``  accepts a GTFS ``.zip``, validates + ingests it into
  a throwaway SQLite db, picks a simulation window inside the feed's own
  calendar validity, simulates ridership, and returns the dashboard HTML.

Deploy with the environment variable ``DEMO_DB`` pointing at a pre-built
database file to skip regenerating the demo on every cold start; otherwise
one is built into a temp directory automatically.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import zipfile
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Import the transit-analytics package (sibling directory) without requiring
# it to be pip-installed in the deploy environment.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from transit_analytics import dashboard, gtfs, ridership, sample_feed  # noqa: E402

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
CACHE_CAPACITY = 25

app = FastAPI(
    title="Transit Analytics API",
    description="Upload a GTFS feed (or use the bundled demo) and get back "
    "a self-contained HTML ridership dashboard.",
    version="0.2.0",
)

# CORS for the Vercel frontend. allow_credentials must stay False alongside
# a wildcard origin — browsers reject that combination outright, and we
# don't use cookies/auth here anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class _LRUCache:
    """Tiny in-memory LRU cache: content-hash -> rendered dashboard HTML.

    Re-analyzing a feed a user already uploaded (retry, page refresh, a
    popular public feed multiple people upload) becomes instant instead of
    re-running ingestion + simulation. Best-effort only — an in-memory
    cache is naturally cleared on cold start / redeploy, which is fine.
    """

    def __init__(self, capacity: int):
        self._capacity = capacity
        self._data: "OrderedDict[str, str]" = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._capacity:
                self._data.popitem(last=False)


_cache = _LRUCache(CACHE_CAPACITY)


def _build_demo_db() -> str:
    demo_dir = Path(tempfile.gettempdir()) / "transit_demo"
    demo_dir.mkdir(exist_ok=True)
    db_path = demo_dir / "demo.db"
    if not db_path.exists():
        feed_dir = demo_dir / "gtfs"
        sample_feed.build_feed(feed_dir)
        conn = gtfs.connect(db_path)
        gtfs.load_feed(feed_dir, conn)
        start, days = gtfs.pick_simulation_window(conn)
        ridership.simulate(conn, start=start, days=days, seed=42)
        conn.close()
    return str(db_path)


DEMO_DB = os.environ.get("DEMO_DB") or _build_demo_db()


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "transit-analytics-api",
        "endpoints": ["/api/health", "/api/demo", "/api/upload", "/docs"],
    }


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get(
    "/api/demo",
    response_class=HTMLResponse,
    tags=["dashboard"],
    summary="Get the pre-built demo dashboard",
)
def demo():
    """Render the dashboard for the bundled Sound Transit-modeled sample feed."""
    try:
        conn = gtfs.connect(DEMO_DB)
        html = dashboard.render(conn, title="Transit Analytics (Demo Data)")
        conn.close()
        return html
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Demo generation failed: {exc}")


@app.post(
    "/api/upload",
    response_class=HTMLResponse,
    tags=["dashboard"],
    summary="Analyze an uploaded GTFS feed",
)
async def upload(file: UploadFile = File(...)):
    """Ingest an uploaded GTFS ``.zip``, simulate ridership, return the dashboard.

    Returns 400 with a specific reason if the archive isn't a valid zip, is
    missing required GTFS files/columns, or has no routes. Returns 413 if
    the upload exceeds the size limit.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) / 1e6:.1f} MB, max "
            f"{MAX_UPLOAD_BYTES / 1e6:.0f} MB)",
        )

    cache_key = hashlib.sha256(content).hexdigest()
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            feed_zip = tmpdir / "feed.zip"
            feed_zip.write_bytes(content)

            if not zipfile.is_zipfile(feed_zip):
                raise HTTPException(
                    status_code=400, detail="File is not a valid .zip archive"
                )

            db_path = tmpdir / "transit.db"
            conn = gtfs.connect(str(db_path))
            try:
                gtfs.load_feed(feed_zip, conn)
            except gtfs.GTFSValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

            n_routes = conn.execute(
                "SELECT COUNT(*) AS n FROM routes"
            ).fetchone()["n"]
            if n_routes == 0:
                raise HTTPException(
                    status_code=400, detail="Feed has no routes after parsing"
                )

            start, days = gtfs.pick_simulation_window(conn)
            ridership.simulate(conn, start=start, days=days, seed=42)

            html = dashboard.render(
                conn, title=f"Transit Analytics — {file.filename}"
            )
            conn.close()

        _cache.put(cache_key, html)
        return html

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
