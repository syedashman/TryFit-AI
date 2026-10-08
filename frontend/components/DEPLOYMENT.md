# Deploying TryFit AI on Netlify and Render

Stack:
- **Frontend (Next.js)** → **Netlify**
- **Backend (FastAPI)** → **Render**

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
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
3. Under **Environment → Secret Files**, add a file:
   - **Filename:** `/etc/secrets/gcp-key.json`
   - **Contents:** paste the full JSON from Step 2.
4. Under **Environment → Environment Variables**, add every key from your
   local `backend/.env`, plus:
   - `GOOGLE_APPLICATION_CREDENTIALS` = `/etc/secrets/gcp-key.json`
   - `APP_ENV` = `production`
   - `CORS_ORIGINS` = `["https://your-app-name.netlify.app"]` (you'll get
     this exact URL in Step 4 — come back and update this after).
   - `CORS_ORIGIN_REGEX` = `https://[a-z0-9-]+\.netlify\.app` for deploy previews.
   - `MAX_CONCURRENT_JOBS` = `1` on small Render instances; increase only
     after checking memory headroom.
5. Click **Create Web Service**. First deploy takes a few minutes. You'll
   get a URL like `https://tryfit-ai-backend.onrender.com`.
6. Set **Health Check Path** to `/api/health`.
7. Test it: open `https://tryfit-ai-backend.onrender.com/api/health` in a
   browser — should return the same JSON you saw locally.

---

## 4. Deploy the frontend on Netlify

1. Create a site from the GitHub repository in **Netlify**. The included
   `netlify.toml` sets `frontend` as the base directory and enables the
   Next.js plugin.
2. Under **Site configuration → Environment variables**, set:
   - `NEXT_PUBLIC_API_BASE_URL` = your Render backend URL from Step 3
     (for example, `https://tryfit-ai-backend.onrender.com`, with no trailing
     slash).
3. Deploy. Note the site's `https://<site-name>.netlify.app` URL. Public
   Next.js variables are embedded at build time, so changing this value
   requires a new frontend deploy.

---

## 5. Close the loop — update CORS

Go back to Render → your backend service → Environment and set
`CORS_ORIGINS` to your production Netlify URL and any custom domain, for
example:

```
CORS_ORIGINS=["https://your-site.netlify.app","https://tryfit.example.com"]
```

The backend also allows HTTPS `*.netlify.app` deploy-preview origins using
`CORS_ORIGIN_REGEX`; set this explicitly on Render if you override the
default. Custom domains must be listed in `CORS_ORIGINS`. Save the changes
and Render will redeploy. Missing `NEXT_PUBLIC_API_BASE_URL` no longer
falls back to localhost in production.

---

## 6. Test the auto-deploy loop

Make any small change locally (e.g. edit text in `app/page.tsx`), then:

```bash
git add .
git commit -m "test auto deploy"
git push
```

Watch the Render and Netlify dashboards — both should start a new deploy
within seconds, with no manual steps. Once live, refresh the site to see
the change.

---

## 7. Custom domain (optional, later)

Both Render and Netlify let you attach your own domain (you only
pay for the domain itself, not the hosting). Do this once you're ready to
share the demo under your own brand name instead of `.onrender.com` /
`.netlify.app`.