from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.job_scheduler import job_scheduler
from app.services.storage import ensure_storage
from app.services.memory_metrics import log_memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(
        f"[TRYFIT EFFECTIVE CONFIG] fast_mode={settings.tryfit_fast_mode} "
        f"max_dimension={settings.effective_max_image_dimension} "
        f"candidate_count={settings.effective_candidate_count} "
        f"concurrency={settings.effective_concurrency} "
        f"max_rounds={settings.effective_max_generation_rounds} "
        f"debug_dumps={settings.effective_debug_image_dumps}"
    )
    print(
        f"[STARTUP] storage={settings.storage_dir} "
        f"workers={settings.effective_concurrency} "
        f"fast_mode={settings.tryfit_fast_mode}"
    )
    log_memory("startup")
    ensure_storage(settings)
    job_scheduler.configure(max_workers=max(1, min(settings.effective_concurrency, 2)))
    try:
        yield
    finally:
        print("[SHUTDOWN] TryFit worker scheduler stopping")
        job_scheduler.shutdown()


configure_logging()
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="4.3.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)


@app.get("/app", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent / "static" / "index.html")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "TryFit AI backend is running.",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
