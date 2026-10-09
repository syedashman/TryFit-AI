from contextlib import asynccontextmanager
import logging
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
from app.services.http_client import close_http_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "Starting TryFit fast_mode=%s max_dimension=%s candidates=%s workers=%s",
        settings.tryfit_fast_mode,
        settings.effective_max_image_dimension,
        settings.effective_candidate_count,
        settings.effective_concurrency,
    )
    log_memory("startup")
    ensure_storage(settings)
    job_scheduler.configure(max_workers=max(1, min(settings.effective_concurrency, 2)))
    try:
        yield
    finally:
        logger.info("Stopping TryFit workers")
        job_scheduler.shutdown()
        close_http_client()


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
    allow_origin_regex=settings.cors_origin_regex,
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
