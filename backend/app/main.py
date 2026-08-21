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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_storage(settings)
    job_scheduler.configure(max_workers=max(1, min(settings.max_concurrent_jobs, 3)))
    try:
        yield
    finally:
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
