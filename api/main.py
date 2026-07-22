"""FastAPI backend for transit-analytics web app.

Deploy to Railway/Fly.io with environment variable DEMO_DB pointing to
the demo database file, or it will generate one on startup.
"""

import os
import tempfile
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Import the transit-analytics package (sibling directory)
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from transit_analytics import dashboard, gtfs, ridership, sample_feed

app = FastAPI(title="Transit Analytics API")

# CORS for the Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache the demo database path
DEMO_DB = os.environ.get("DEMO_DB")
if not DEMO_DB:
    # Generate on startup
    demo_dir = Path(tempfile.gettempdir()) / "transit_demo"
    demo_dir.mkdir(exist_ok=True)
    DEMO_DB = str(demo_dir / "demo.db")
    # Only build if it doesn't exist
    if not Path(DEMO_DB).exists():
        feed_dir = demo_dir / "gtfs"
        sample_feed.build_feed(feed_dir)
        conn = gtfs.connect(DEMO_DB)
        gtfs.load_feed(feed_dir, conn)
        ridership.simulate(conn, start=date(2026, 3, 2), days=28, seed=42)
        conn.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/demo", response_class=HTMLResponse)
def demo():
    """Return the pre-built demo dashboard."""
    try:
        conn = gtfs.connect(DEMO_DB)
        html = dashboard.render(conn, title="Transit Analytics (Demo Data)")
        conn.close()
        return html
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload", response_class=HTMLResponse)
async def upload(file: UploadFile = File(...)):
    """Accept a GTFS zip, process it, and return the dashboard HTML."""
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files accepted")

    if file.size and file.size > 50 * 1024 * 1024:  # 50 MB
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            # Save uploaded file
            feed_zip = tmpdir / "feed.zip"
            content = await file.read()
            feed_zip.write_bytes(content)

            # Create database and ingest
            db_path = tmpdir / "transit.db"
            conn = gtfs.connect(str(db_path))
            try:
                gtfs.load_feed(feed_zip, conn)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid GTFS feed: {str(e)}"
                )

            # Check if feed has data
            n_routes = conn.execute("SELECT COUNT(*) AS n FROM routes").fetchone()["n"]
            if n_routes == 0:
                raise HTTPException(status_code=400, detail="Feed has no routes")

            # Simulate ridership
            ridership.simulate(conn, start=date(2026, 3, 2), days=28, seed=42)

            # Generate dashboard
            html = dashboard.render(
                conn,
                title=f"Transit Analytics - {file.filename}"
            )
            conn.close()
            return html

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
