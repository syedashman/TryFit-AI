# TryFit AI — Sprint 4 Phase 1

## Delivered

- Thread-safe provider runtime registry
- Retry policy with exponential backoff
- Automatic Vertex → CatVTON fallback
- Circuit breaker for repeatedly failing providers
- Provider health caching
- Success, failure, retry and latency metrics
- `/api/runtime/metrics` endpoint
- `/api/runtime/diagnostics` endpoint
- Sprint/version health metadata updated to Sprint 4 Phase 1
- New regression tests for runtime behavior

## Run

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m pytest
python -m uvicorn app.main:app --reload
```

## Diagnostics

- `http://127.0.0.1:8000/api/health`
- `http://127.0.0.1:8000/api/runtime/metrics`
- `http://127.0.0.1:8000/api/runtime/diagnostics`
- `http://127.0.0.1:8000/docs`
