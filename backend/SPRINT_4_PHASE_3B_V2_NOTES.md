# TRYFIT AI — Sprint 4 Phase 3B V2

## Included
- Completely redesigned Studio UI.
- Men, Women and Kids catalog sections.
- 33 catalog products and 179 supplied garment reference images.
- Product colors and reference poses are discovered from folders automatically.
- Batch generation: one backend job per selected garment reference.
- The UI reserves and displays exactly one output card per generated job.
- Selecting All Colors generates every color and pose for that product.
- Single clean results area only; no before/after slider and no history UI.
- Progress is hidden initially and starts at 0% only after a valid Generate action.
- Individual fullscreen preview and download for every completed result.
- Age-neutral application policy: no app-level newborn/adult/elderly age filter.

## Important provider note
The application does not impose an age restriction. Actual generation still depends on the configured provider's safety policy, image quality requirements and model capability.

## Run
1. Open `backend`.
2. Activate the existing virtual environment or install `requirements.txt`.
3. Confirm `.env` contains valid Vertex credentials/settings.
4. Run: `uvicorn app.main:app --reload --port 8001`
5. Open: `http://127.0.0.1:8001/app`

## Verification
- Backend tests: 72 passed.
- JavaScript syntax: passed.
- Catalog API: 33 products / 179 images.
