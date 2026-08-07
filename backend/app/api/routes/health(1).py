from fastapi import APIRouter

from app.core.config import get_settings
from app.providers.factory import get_vton_provider

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "sprint": "4",
        "phase": "3A",
        "provider": settings.vton_provider,
        "release": "Sprint 4 Phase 3B V2",
        "catalog_batch_generation": True,
        "age_neutral_application_validation": True,
    }

