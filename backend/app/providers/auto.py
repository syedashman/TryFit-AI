from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.providers.base import (
    ProviderConfigurationError,
    ProviderError,
    TryOnRequest,
    TryOnResult,
    VTONProvider,
)
from app.providers.factory import get_named_provider
from app.services.provider_runtime import provider_runtime


class AutoFallbackProvider(VTONProvider):
    name = "auto"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def health(self) -> dict[str, Any]:
        providers: list[dict[str, Any]] = []
        for name in self.settings.provider_fallback_order:
            try:
                provider = get_named_provider(name, self.settings)
                item = provider_runtime.cached_health(
                    name,
                    provider.health,
                    ttl_seconds=self.settings.provider_health_cache_ttl_seconds,
                )
                item["circuit_open"] = provider_runtime.is_circuit_open(name)
                providers.append(item)
            except ProviderError as exc:
                providers.append({
                    "provider": name,
                    "configured": False,
                    "error": exc.to_dict(),
                })
            except Exception as exc:
                providers.append({
                    "provider": name,
                    "configured": False,
                    "error": {
                        "message": str(exc),
                        "code": "health_check_failed",
                    },
                })

        configured_count = sum(
            1 for item in providers if bool(item.get("configured", False))
        )
        return {
            "provider": self.name,
            "configured": configured_count > 0,
            "order": list(self.settings.provider_fallback_order),
            "configured_provider_count": configured_count,
            "providers": providers,
            "runtime": provider_runtime.snapshot(),
        }

    def generate(self, request: TryOnRequest) -> TryOnResult:
        failures: list[dict[str, Any]] = []

        for name in self.settings.provider_fallback_order:
            try:
                provider = get_named_provider(name, self.settings)
                result = provider_runtime.execute(
                    name,
                    lambda provider=provider: provider.generate(request),
                    max_retries=self.settings.provider_runtime_max_retries,
                    backoff_seconds=self.settings.provider_runtime_backoff_seconds,
                    failure_threshold=self.settings.provider_failure_threshold,
                    cooldown_seconds=self.settings.provider_circuit_cooldown_seconds,
                )
                original_endpoint = result.endpoint_used
                result.endpoint_used = (
                    f"{name}:{original_endpoint}" if original_endpoint else name
                )
                result.metadata.setdefault("provider", name)
                result.metadata["fallback_provider"] = name
                result.metadata["fallback_order"] = list(
                    self.settings.provider_fallback_order
                )
                result.metadata["provider_runtime"] = provider_runtime.snapshot().get(name, {})
                return result
            except ProviderConfigurationError:
                raise
            except ProviderError as exc:
                failures.append({"provider": name, "error": exc.to_dict()})

        if not failures:
            raise ProviderConfigurationError("No fallback providers are configured.")

        summary = " | ".join(
            f"{item['provider']} [{item['error']['code']}]: {item['error']['message']}"
            for item in failures
        )
        raise ProviderError(
            f"All configured providers failed. {summary}",
            code="all_providers_failed",
            provider=self.name,
            retryable=any(bool(item["error"].get("retryable", False)) for item in failures),
            details={
                "order": list(self.settings.provider_fallback_order),
                "failures": failures,
                "runtime": provider_runtime.snapshot(),
            },
        )
