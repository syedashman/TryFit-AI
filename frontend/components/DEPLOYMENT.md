# Deploying TryFit AI (free, auto-deploy on every push)

Stack:
- **Frontend (Next.js)** → **Vercel** (free Hobby tier)
- **Backend (FastAPI)** → **Render** (free Web Service tier)

Both platforms redeploy automatically every time you push to your GitHub
repo's connected branch — that covers "jo bhi kaam yahan se karenge woh
deployed pe trigger ho."

---

## 0. Known limitation on the free backend tier (read first)

Render's free tier **spins the service down after 15 minutes of no
traffic**, and cold-starts take 30–60s on the next request. Its disk is
**ephemeral** — any files your backend writes locally (uploaded photos,
generated results in `storage/`) disappear on every redeploy or restart.
For a demo this is fine (results are shown to the user immediately and
downloaded, not meant to persist long-term). If you later need persistence,
move `storage/` to Google Cloud Storage — ask me when you get there.

---

## 1. Put the code on GitHub

```bash
cd TryFitAI
git init
git add .
git commit -m "Initial TryFit AI commit"
```

Create a new **empty** repo on github.com (no README/gitignore — you
already have one), then:

```bash
git remote add origin https://github.com/<your-username>/tryfit-ai.git
git branch -M main
git push -u origin main
```

The `.gitignore` already in this project excludes `venv/`, `node_modules/`,
`.next/`, and both `.env` files — your secrets never get pushed. Good.

---

## 2. Create a GCP Service Account (server can't use `gcloud login`)

`gcloud auth application-default login` only works on your own machine.
A deployed server needs a **service account key** instead:

1. Go to **console.cloud.google.com** → your `tryfit-ai-503322` project →
   **IAM & Admin → Service Accounts → Create Service Account**.
2. Name it e.g. `tryfit-backend`. Grant it the role **Vertex AI User**.
3. Open the new service account → **Keys** tab → **Add Key → Create new
   key → JSON**. This downloads a `.json` file — keep it safe, don't commit
   it to Git.

---

## 3. Deploy the backend on Render

1. Sign up at **render.com** (no card needed) → **New → Web Service** →
   connect your GitHub repo.
2. Configure:
   - **Root Directory:** `backend`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Under **Environment → Secret Files**, add a file:
   - **Filename:** `/etc/secrets/gcp-key.json`
   - **Contents:** paste the full JSON from Step 2.
4. Under **Environment → Environment Variables**, add every key from your
   local `backend/.env`, plus:
   - `GOOGLE_APPLICATION_CREDENTIALS` = `/etc/secrets/gcp-key.json`
   - `CORS_ORIGINS` = `["https://your-app-name.vercel.app"]` (you'll get
     this exact URL in Step 4 — come back and update this after).
5. Click **Create Web Service**. First deploy takes a few minutes. You'll
   get a URL like `https://tryfit-ai-backend.onrender.com`.
6. Test it: open `https://tryfit-ai-backend.onrender.com/api/health` in a
   browser — should return the same JSON you saw locally.

---

## 4. Deploy the frontend on Vercel

1. Sign up at **vercel.com** with GitHub → **Add New → Project** → import
   the same repo.
2. Set **Root Directory** to `frontend`.
3. Add an Environment Variable:
   - `NEXT_PUBLIC_API_BASE_URL` = your Render backend URL from Step 3
     (e.g. `https://tryfit-ai-backend.onrender.com`)
4. Deploy. You'll get a URL like `https://tryfit-ai.vercel.app`.

---

## 5. Close the loop — update CORS

Go back to Render → your backend service → Environment → update
`CORS_ORIGINS` to your real Vercel URL from Step 4:

```
CORS_ORIGINS=["https://tryfit-ai.vercel.app"]
```

Save — Render redeploys automatically. Without this step the frontend can
load, but API calls will fail with a CORS error in the browser console.

---

## 6. Test the auto-deploy loop

Make any small change locally (e.g. edit text in `app/page.tsx`), then:

```bash
git add .
git commit -m "test auto deploy"
git push
```

Watch the Render and Vercel dashboards — both should start a new deploy
within seconds, with no manual steps. Once live, refresh the site to see
the change.

---

## 7. Custom domain (optional, later)

Both Render and Vercel let you attach your own domain for free (you only
pay for the domain itself, not the hosting). Do this once you're ready to
share the demo under your own brand name instead of `.onrender.com` /
`.vercel.app`.