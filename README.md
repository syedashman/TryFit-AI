# TryFit AI — Demo Storefront + Virtual Try-On Backend

This package has two parts:

- **`backend/`** — FastAPI service that talks to Google Vertex AI's Virtual
  Try-On model (with a CatVTON fallback). This was already built in earlier
  sprints; it's included here unchanged (minus the old venv, cache files,
  and generated test data).
- **`frontend/`** — a brand-new Next.js (React) storefront demo, built to
  match the flow you described: category tabs (Men / Women / Kids), product
  cards, a product detail page with **Add to Cart**, **Add to Favourite**,
  and **Try Fit Now** buttons, and a Try Fit Now flow that opens in a new
  window where the shopper uploads 3–5 photos and sees the generated result.

This is a **demo shell**, not yet a plugin that installs on someone else's
Shopify/WooCommerce/custom store. It's built so you (and whoever you show
this to — your co-founder, an investor, a brand) can click through the real
experience end to end and judge the output quality. The embeddable
plugin/widget layer is the next phase, once you're happy with generation
quality.

---

## 1. Before you start: Vertex AI billing (read this)

You mentioned wanting to use the "free tier" for the demo. To set
expectations correctly: **Vertex AI's Virtual Try-On model does not have an
ongoing free tier** — it's billed per generated image. What Google does
offer:

- New Google Cloud accounts get a **free trial credit** (currently $300,
  valid ~90 days at the time of writing) that you can use to cover demo
  generations. Check the current offer at
  https://cloud.google.com/free — terms change, so verify before you rely
  on it.
- Outside of that trial credit, every image this backend generates through
  Vertex will incur a small charge on your GCP billing account. There is no
  way to call the Virtual Try-On model with zero cost once trial credit
  runs out.

Practically: enable billing on your GCP project (required even to use trial
credit), and keep an eye on usage while you demo this to brand owners.

---

## 2. Backend setup

```bash
cd backend
python -m venv venv

# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

**Google Cloud auth** (one-time):

```bash
gcloud auth application-default login
```

This opens a browser login and stores credentials the backend will pick up
automatically. Make sure the GCP project in `backend/.env`
(`GOOGLE_CLOUD_PROJECT`) matches a project where:
- Billing is enabled
- The Vertex AI API is enabled (APIs & Services → Enable APIs → "Vertex AI API")

**Run the tests** (should show `80 passed`):

```bash
python -m pytest -q
```

**Start the server:**

```bash
uvicorn app.main:app --reload --port 8001
```

Leave this running. API docs live at `http://127.0.0.1:8001/docs`.

---

## 3. Frontend setup

Open a **second terminal**:

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`. You should see the storefront with Men /
Women / Kids tabs and the demo catalog (33 products) pulled live from your
backend.

To build for production (this is what you'd deploy):

```bash
npm run build
npm run start
```

---

## 4. Trying the actual flow

1. On the homepage, click any product.
2. On the product page, click **✨ Try Fit Now** — a new window opens.
3. Upload 3 to 5 clear photos of yourself (good lighting, face + body
   visible) and click **Generate my try-on**.
4. Wait — Vertex generation typically takes 10–60 seconds per image. The
   window polls the backend automatically and shows the result(s) when
   ready.

If a generation fails, the card will show the reason (e.g. photo quality
rejected, Vertex error) instead of a blank state — that's the backend's
person-validation and error-handling logic surfacing, not a frontend bug.

---

## 5. What's real vs. what's still a demo shortcut

**Real:**
- The Vertex AI Virtual Try-On call, retry logic, candidate ranking, and
  person-photo validation — this is genuine generation, not mocked.
- The catalog, product detail, and try-on UI — fully functional against
  your backend.

**Demo shortcuts** (expected, and fine for showing quality/UX to people
before you invest in the next phase):
- Add to Cart / Add to Favourite are local UI state only — no real cart,
  no persistence, no accounts.
- The catalog is your own bundled sample images, not a live Khaadi-style
  product feed.
- Everything runs on one machine, for one user, with no multi-tenant
  billing or API-key system — that's the SaaS/plugin layer for next phase.

---

## 6. Known limitation (not a bug)

Vertex's Virtual Try-On model preserves the **pose of the person photo you
upload**, not the pose of the garment's original model shot. If a result
looks slightly stiff on some angles, that's the underlying Google model's
behavior, not something wrong in this codebase.

## 7. Runtime and persistence notes

Catalog jobs are executed in-process by a bounded `ThreadPoolExecutor`. The
default is `MAX_CONCURRENT_JOBS=2` (configurable from 1 to 3), so independent
uploaded photos can run concurrently without creating unlimited provider
requests. One Vertex request asks for `VERTEX_CANDIDATE_COUNT` candidates
(3 by default); the quality policy allows at most two same-photo generation
rounds, and provider HTTP retries are separately controlled by
`VERTEX_MAX_RETRIES`.

Job and batch state is stored as JSON files under `backend/storage/jobs`, with
uploads and results under the same local storage directory. There is no
database or remote state store in this project. A Render restart or redeploy
can therefore lose in-process work and local state unless the service uses a
persistent Render disk mounted at the configured storage path. The frontend
clears expired batch references instead of treating a missing batch as a photo
failure.

Generation logs now include normalization, validation, each Vertex round,
provider-call count, retry count, candidate count, total job time, and total
batch time. Real provider measurements require a configured Vertex deployment;
the automated tests do not claim a production latency before/after number.
