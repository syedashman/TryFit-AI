from fastapi import APIRouter

from app.core.config import get_settings
from app.providers.factory import get_vton_provider
from app.services.provider_runtime import provider_runtime

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/metrics")
def runtime_metrics() -> dict[str, object]:
    settings = get_settings()
    return {
        "sprint": "4",
        "phase": "3A",
        "provider": settings.vton_provider,
        "fallback_order": list(settings.provider_fallback_order),
        "metrics": provider_runtime.snapshot(),
    }


@router.get("/diagnostics")
def runtime_diagnostics() -> dict[str, object]:
    settings = get_settings()
    provider = get_vton_provider(settings)
    return {
        "sprint": "4",
        "phase": "3A",
        "provider_health": provider.health(),
        "runtime_metrics": provider_runtime.snapshot(),
        "retry_policy": {
            "max_retries": settings.provider_runtime_max_retries,
            "backoff_seconds": settings.provider_runtime_backoff_seconds,
            "failure_threshold": settings.provider_failure_threshold,
            "circuit_cooldown_seconds": settings.provider_circuit_cooldown_seconds,
            "health_cache_ttl_seconds": settings.provider_health_cache_ttl_seconds,
        },
    }
