from __future__ import annotations

from app.core.config import Settings
from app.providers.base import (
    ProviderConfigurationError,
    VTONProvider,
)
from app.providers.catvton import CatVTONProvider
from app.providers.vertex import VertexTryOnProvider


SUPPORTED_PROVIDERS = {
    "catvton",
    "vertex",
    "auto",
}


def normalize_provider_name(
    name: str,
) -> str:
    normalized = name.strip().lower()

    if not normalized:
        raise ProviderConfigurationError(
            "VTON provider name cannot be blank."
        )

    if normalized not in SUPPORTED_PROVIDERS:
        raise ProviderConfigurationError(
            (
                f"Unsupported VTON provider: {name}. "
                "Supported providers are "
                "auto, vertex, and catvton."
            ),
            details={
                "requested_provider": name,
                "supported_providers": sorted(
                    SUPPORTED_PROVIDERS
                ),
            },
        )

    return normalized


def get_named_provider(
    name: str,
    settings: Settings,
) -> VTONProvider:
    normalized = normalize_provider_name(name)

    if normalized == "catvton":
        return CatVTONProvider(settings)

    if normalized == "vertex":
        return VertexTryOnProvider(settings)

    if normalized == "auto":
        from app.providers.auto import (
            AutoFallbackProvider,
        )

        return AutoFallbackProvider(settings)

    raise ProviderConfigurationError(
        f"Unsupported VTON provider: {name}"
    )


def get_vton_provider(
    settings: Settings,
) -> VTONProvider:
    return get_named_provider(
        settings.vton_provider,
        settings,
    )