from fastapi import APIRouter

from app.api.routes import health, jobs, provider, runtime, catalog, intelligence

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(provider.router)
api_router.include_router(runtime.router)
api_router.include_router(jobs.router)
api_router.include_router(catalog.router)
api_router.include_router(intelligence.router)
