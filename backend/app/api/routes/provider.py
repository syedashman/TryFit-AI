from fastapi import APIRouter

from app.core.config import get_settings
from app.providers.factory import get_named_provider, get_vton_provider

router = APIRouter(prefix="/provider", tags=["provider"])


@router.get("")
def provider_status():
    settings = get_settings()
    provider = get_vton_provider(settings)
    return provider.health()


@router.get("/{provider_name}")
def named_provider_status(provider_name: str):
    settings = get_settings()
    provider = get_named_provider(provider_name, settings)
    return provider.health()
