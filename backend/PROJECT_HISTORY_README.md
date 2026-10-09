# TryFit AI — Sprint 3.3 Phase 4 Complete Final

Cumulative commercial backend with Google Vertex Virtual Try-On as primary provider.

## Final Phase-4 behaviour
- Requires 3–5 photos of the same person.
- Separates identity, geometry, and pose references.
- For predefined front/side poses, Gemini receives the user's image and text pose instructions only; bundled pose-reference photos are not used as appearance inputs.
- When local checks trigger identity review, TryFit sends full source/result images plus enlarged face crops when detectable so facial features are compared at useful scale.
- If all predefined-pose try-on candidates fail the existing quality gates, TryFit makes one final attempt using the original uploaded photo and records that pose fallback in job metadata.
- Uses geometry-aware person detection instead of canvas aspect ratio alone.
- For `overall` and `lower` garments, the best true full-body/three-quarter photo is sent to Vertex.
- For `upper` garments, the best compatible upper-body/identity reference is used.
- Requests 3 official Vertex candidates and ranks them for height compression, body widening, shoulder widening, and torso widening.
- Includes a ready-to-use `.env` for project `tryfit-ai-503322`. ADC authentication is still required on the machine.

## Run
```powershell
cd backend
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest
uvicorn app.main:app --reload --port 8001
```

Swagger: `http://127.0.0.1:8001/docs`

Provider check:
```powershell
python -c "from app.core.config import get_settings; get_settings.cache_clear(); s=get_settings(); print('project:', s.google_cloud_project); print('provider:', s.vton_provider); print('candidates:', s.vertex_candidate_count)"
```
