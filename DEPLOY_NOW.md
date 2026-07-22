# Deploy Transit Analytics in 5 minutes

Two platforms, zero cost forever (within free tier limits).

## Step 1: Backend on Railway (2 minutes)

1. Go to https://railway.app
2. Click **New Project** → **Deploy from GitHub**
3. Sign in with GitHub, select `ctanya-rani/transit-ridership-analysis`
4. Choose the branch `claude/transit-ridership-analytics-meva5z`
5. Click **Deploy**
6. Wait for the build to complete
7. Go to **Deployments** → click your deployment
8. In **Domains**, enable a public domain (you'll get something like `transit-analytics-production.railway.app`)
9. **Copy this domain** — you'll need it for the frontend

## Step 2: Frontend on Vercel (2 minutes)

1. Go to https://vercel.com
2. Click **Add New** → **Project**
3. **Import GitHub Project**, select `transit-ridership-analysis`
4. Under **Root Directory**, set to `web/`
5. Click **Environment Variables** and add:
   ```
   Name:  NEXT_PUBLIC_API_URL
   Value: https://transit-analytics-production.railway.app
   ```
   (Replace with your actual Railway domain from Step 1)
6. Click **Deploy**
7. Wait ~2 minutes for Vercel to build
8. You'll get a live URL like `transit-analytics-web.vercel.app` — **share this link!**

---

## What you can do now

✅ Load the **demo dataset** instantly (30 seconds)  
✅ Upload any **GTFS feed** (.zip file) and analyze it (30–60 seconds)  
✅ Get a **light/dark dashboard** with interactive charts  
✅ Share the link with anyone — no sign-up needed  

---

## Free tier details

- **Railway**: 500 hours/month (enough for ~24/7 operation)
- **Vercel**: unlimited deployments & bandwidth
- **No credit card required** (Railway asks for one but doesn't charge)

---

## Troubleshooting

**"API is down" error?**
- Check Railroad dashboard: **Deployments** → is there a green ✓?
- If red, click to see logs; usually a Python import error (check `api/requirements.txt`)

**"NEXT_PUBLIC_API_URL is wrong"?**
- Make sure it's the Railway **Domains** URL, not your GitHub link
- Redeploy Vercel after changing it (Vercel → Redeploy)

**Upload times out?**
- Railway free tier has 10-minute function timeout, large feeds can exceed it
- Smaller feeds (< 10 MB) work instantly

---

## Next steps (optional)

- **Custom domain**: both platforms support CNAME at your domain registrar
- **Database persistence**: Railway's Postgres add-on (~$5/mo) if you want to cache uploads
- **Real GTFS data**: find feeds at https://transit.land/ or agency websites
