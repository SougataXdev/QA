# Deployment Guide — QA Dashboard

This guide deploys three services for free:

| Service                                                | Platform | What it does                            |
| ------------------------------------------------------ | -------- | --------------------------------------- |
| **Redis**                                              | Render   | Job queue + status store                |
| **Backend** (FastAPI API + ARQ Worker, single service) | Render   | PDF extraction, web scraping, QA checks |
| **Frontend** (Next.js)                                 | Vercel   | Dashboard UI                            |

> **Architecture note:** The API and Worker run as two processes inside a single Render Web Service using [honcho](https://github.com/nickstenning/honcho) (a Python Procfile runner). This keeps things simple — one service, one deploy, one set of logs.

---

## Prerequisites

- A GitHub account with this repo pushed to it
- A [Render](https://render.com) account (sign up free with GitHub)
- A [Vercel](https://vercel.com) account (sign up free with GitHub)

---

## Part 1 — Push to GitHub

If your repo is not on GitHub yet:

```bash
cd /path/to/QA
git add -A
git commit -m "Prepare for deployment"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

---

## Part 2 — Redis on Render (Free)

1. Go to [https://dashboard.render.com](https://dashboard.render.com)
2. Click **New** (top right) → **Redis**
3. Fill in:
   - **Name:** `qa-redis`
   - **Region:** Pick the one closest to you (e.g. Oregon, Frankfurt)
   - **Plan:** Free
4. Click **Create Redis**
5. Wait for it to spin up (~30 seconds)
6. On the Redis page, find **Internal URL** — it looks like:
   ```
   redis://red-abc123xyz:6379
   ```
7. **Copy this URL.** You will paste it into both backend services below.

> **Note:** The "Internal URL" only works between Render services in the same account. This is what you want — it's faster and free.

---

## Part 3 — Backend on Render (API + Worker in one service)

Both the FastAPI API and the ARQ Worker run together in a single Render Web Service using **honcho** and a `Procfile`.

Your repo already has:

- `Procfile` (repo root) — defines the two processes
- `honcho` in `pdf_engine/requirements.txt` — the process runner

1. Go to [https://dashboard.render.com](https://dashboard.render.com)
2. Click **New** → **Web Service**
3. Connect your GitHub repo (authorize Render if prompted)
4. Select your QA repo
5. Fill in the settings:

| Field              | Value                                                                                   |
| ------------------ | --------------------------------------------------------------------------------------- |
| **Name**           | `qa-api`                                                                                |
| **Region**         | Same region as your Redis                                                               |
| **Branch**         | `main`                                                                                  |
| **Root Directory** | _(leave empty)_                                                                         |
| **Runtime**        | `Python 3`                                                                              |
| **Build Command**  | `pip install -r pdf_engine/requirements.txt && playwright install --with-deps chromium` |
| **Start Command**  | `honcho start`                                                                          |
| **Plan**           | Free                                                                                    |

> **Why `honcho start`?** It reads the `Procfile` and launches both processes:
> ```
> web: uvicorn pdf_engine.main:app --host 0.0.0.0 --port $PORT
> worker: python -m arq pdf_engine.worker.WorkerSettings
> ```

6. Scroll down to **Environment Variables**, click **Add Environment Variable**:

| Key         | Value                                                                  |
| ----------- | ---------------------------------------------------------------------- |
| `REDIS_URL` | Paste the Internal URL from Part 2 (e.g. `redis://red-abc123xyz:6379`) |

7. Click **Create Web Service**
8. Wait for the build to complete (~3-5 minutes, Playwright downloads Chromium)
9. In the logs, you should see both processes start:
   ```
   web.1    | Uvicorn running on http://0.0.0.0:XXXX
   worker.1 | Starting worker for 1 functions
   ```
10. Once deployed, Render gives you a public URL like:
    ```
    https://qa-api-xxxx.onrender.com
    ```
11. Test it by visiting:
    ```
    https://qa-api-xxxx.onrender.com/health
    ```
    You should see:
    ```json
    { "status": "healthy", "engine": "pdf-qa-extraction", "version": "1.0.0" }
    ```

**Save this URL** — you need it for the frontend deployment.

---

## Part 4 — Frontend on Vercel (Free)

1. Go to [https://vercel.com/dashboard](https://vercel.com/dashboard)
2. Click **Add New...** → **Project**
3. **Import** your GitHub repo
4. On the configure screen, set:

| Field                | Value                                                     |
| -------------------- | --------------------------------------------------------- |
| **Framework Preset** | Next.js (auto-detected)                                   |
| **Root Directory**   | Click **Edit** → type `qa-dashboard` → click **Continue** |

5. Expand **Environment Variables** and add:

| Key                          | Value                                                                     |
| ---------------------------- | ------------------------------------------------------------------------- |
| `NEXT_PUBLIC_PYTHON_API_URL` | Your Render API URL from Part 3 (e.g. `https://qa-api-xxxx.onrender.com`) |

> **Important:** Do NOT add a trailing slash. Use `https://qa-api-xxxx.onrender.com` not `https://qa-api-xxxx.onrender.com/`

6. Click **Deploy**
7. Wait ~1-2 minutes
8. Vercel gives you a live URL like:
   ```
   https://qa-dashboard-xxxx.vercel.app
   ```

Open it in your browser — your QA Dashboard is live.

---

## Verify Everything Works

1. Open your Vercel frontend URL
2. Upload a PDF and enter a target URL
3. Click process
4. Watch the progress bar — it should move through:
   - `Queued → Preflight → Extracting → Scraping → QA Checks → Complete`
5. View the QA report

If the job stays stuck on "Queued", check:

- Render Dashboard → `qa-api` → **Logs** (is the worker process running? Look for `worker.1` lines)
- Render Dashboard → `qa-redis` → **Info** (is Redis active?)
- The `REDIS_URL` env var must be set on `qa-api`

---

## Troubleshooting

### "Job queued but never progresses"

The worker process is not running or not connected to Redis. Check:

1. `qa-api` Logs on Render — look for `worker.1` lines and connection errors
2. Make sure `REDIS_URL` on `qa-api` is the **Internal URL** (starts with `redis://red-`)

### "Network Error" in the browser console

CORS or wrong API URL. Check:

1. Browser DevTools → Network tab → look at the failing request URL
2. Verify `NEXT_PUBLIC_PYTHON_API_URL` on Vercel matches your Render API URL exactly
3. Redeploy on Vercel after changing env vars (env vars only take effect on new deploys)

### First request is slow (~30 seconds)

This is normal on Render's free tier. Free services "sleep" after 15 minutes of inactivity. The first request after sleep triggers a cold start. Subsequent requests are fast.

### Build fails on Render with "playwright" errors

Make sure the **Build Command** on `qa-api` is:

```
pip install -r pdf_engine/requirements.txt && playwright install --with-deps chromium
```

The `--with-deps` flag installs system-level dependencies (fonts, libraries) that Chromium needs.

---

## Architecture Diagram

```
┌──────────────────────┐         ┌──────────────────────────────┐
│   Vercel (free)      │         │   Render Web Service (free)  │
│                      │  HTTPS  │                              │
│  Next.js Frontend    │────────▶│  honcho start                │
│  qa-dashboard/       │         │  ├─ web: FastAPI API         │
│                      │         │  │  POST /process            │
└──────────────────────┘         │  │  GET  /jobs/{id}          │
                                 │  │  GET  /health             │
                                 │  └─ worker: ARQ + Playwright │
                                 │     PDF extract → Scrape     │
                                 │     → QA checks → Report     │
                                 └──────────────┬───────────────┘
                                                │ enqueue / pick up
                                                ▼
                                 ┌──────────────────────────────┐
                                 │  Render Redis (free)         │
                                 │  Job queue + status          │
                                 └──────────────────────────────┘
```

---

## Updating After Code Changes

When you push new code to `main`:

- **Render** auto-redeploys `qa-api` (both API and Worker restart together)
- **Vercel** auto-redeploys the frontend

No manual steps needed after initial setup.
