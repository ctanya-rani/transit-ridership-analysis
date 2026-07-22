# Deploying Transit Analytics

This app has two parts:

1. **Frontend** (Next.js) → deployed to Vercel
2. **Backend** (FastAPI) → deployed to Railway, Fly.io, or similar

## Quick start

### 1. Deploy the backend first (Railway)

[Railway](https://railway.app) is the easiest option.

1. Fork or push this repo to GitHub
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Select the `transit-ridership-analysis` repo
4. Go to Settings → Domains, enable a public domain
5. Copy your domain (e.g., `https://transit-api-production.railway.app`)

### 2. Deploy the frontend (Vercel)

1. Go to https://vercel.com → New Project
2. Import the GitHub repo
3. Set **Root Directory** to `web/`
4. Add environment variable:
   - `NEXT_PUBLIC_API_URL` = your Railway domain (e.g., `https://transit-api-production.railway.app`)
5. Deploy

That's it! You'll get a Vercel URL to share.

---

## Deploy backend to other platforms

### Fly.io

```bash
fly auth login
fly launch --path api
```

Then set the environment variable:
```bash
fly secrets set DEMO_DB=/data/demo.db
```

### Heroku / Render

Both support the `Procfile` in `/api`:

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Just connect your GitHub repo and it deploys automatically.

---

## Local development

Backend:
```bash
cd api
pip install -r requirements.txt
cd ..
pip install -e .
python api/main.py
```

Then in another terminal, frontend:
```bash
cd web
npm install
npm run dev
```

Visit http://localhost:3000 (it connects to http://localhost:8000 for the API).

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` if needed.

---

## How it works

- **`/api/demo`** loads the pre-built demo database (generated on backend startup)
- **`/api/upload`** accepts a GTFS `.zip`, ingests it into SQLite, simulates 28 days of ridership, and returns the HTML dashboard
- The frontend is a simple React app — no build artifacts needed to run the backend
