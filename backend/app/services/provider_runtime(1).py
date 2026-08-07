from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from time import monotonic, sleep
from typing import Any, Callable, TypeVar

from app.providers.base import ProviderError

T = TypeVar("T")


@dataclass(slots=True)
class ProviderStats:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    consecutive_failures: int = 0
    total_latency_ms: float = 0.0
    last_latency_ms: float | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    circuit_open_until: float = 0.0

    def snapshot(self, now: float) -> dict[str, Any]:
        average = (
            self.total_latency_ms / self.attempts
            if self.attempts
            else 0.0
        )
        return {
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "retries": self.retries,
            "consecutive_failures": self.consecutive_failures,
            "success_rate": (
                self.successes / self.attempts
                if self.attempts
                else 0.0
            ),
            "average_latency_ms": round(average, 2),
            "last_latency_ms": (
                round(self.last_latency_ms, 2)
                if self.last_latency_ms is not None
                else None
            ),
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "circuit_open": self.circuit_open_until > now,
            "circuit_retry_after_seconds": round(
                max(0.0, self.circuit_open_until - now), 2
            ),
        }


class ProviderRuntimeRegistry:
    """Thread-safe provider retries, metrics and circuit-breaker state."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._stats: dict[str, ProviderStats] = {}
        self._health_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()
            self._health_cache.clear()

    def is_circuit_open(self, provider: str) -> bool:
        now = monotonic()
        with self._lock:
            return self._stats.setdefault(provider, ProviderStats()).circuit_open_until > now

    def execute(
        self,
        provider: str,
        operation: Callable[[], T],
        *,
        max_retries: int,
        backoff_seconds: float,
        failure_threshold: int,
        cooldown_seconds: float,
    ) -> T:
        if self.is_circuit_open(provider):
            raise ProviderError(
                f"Provider {provider} circuit is temporarily open.",
                code="provider_circuit_open",
                provider=provider,
                retryable=True,
            )

        final_error: ProviderError | None = None
        for attempt in range(max_retries + 1):
            started = monotonic()
            try:
                result = operation()
            except ProviderError as exc:
                elapsed = (monotonic() - started) * 1000.0
                final_error = exc
                with self._lock:
                    stats = self._stats.setdefault(provider, ProviderStats())
                    stats.attempts += 1
                    stats.failures += 1
                    stats.consecutive_failures += 1
                    stats.total_latency_ms += elapsed
                    stats.last_latency_ms = elapsed
                    stats.last_error_code = exc.code
                    stats.last_error_message = str(exc)
                    if stats.consecutive_failures >= failure_threshold:
                        stats.circuit_open_until = monotonic() + cooldown_seconds

                should_retry = exc.retryable and attempt < max_retries
                if not should_retry:
                    raise

                with self._lock:
                    self._stats[provider].retries += 1
                if backoff_seconds > 0:
                    sleep(backoff_seconds * (2**attempt))
            except Exception as exc:
                wrapped = ProviderError(
                    f"Provider {provider} failed unexpectedly: {exc}",
                    code="unexpected_provider_error",
                    provider=provider,
                    retryable=False,
                    details={"exception_type": type(exc).__name__},
                )
                elapsed = (monotonic() - started) * 1000.0
                with self._lock:
                    stats = self._stats.setdefault(provider, ProviderStats())
                    stats.attempts += 1
                    stats.failures += 1
                    stats.consecutive_failures += 1
                    stats.total_latency_ms += elapsed
                    stats.last_latency_ms = elapsed
                    stats.last_error_code = wrapped.code
                    stats.last_error_message = str(wrapped)
                raise wrapped from exc
            else:
                elapsed = (monotonic() - started) * 1000.0
                with self._lock:
                    stats = self._stats.setdefault(provider, ProviderStats())
                    stats.attempts += 1
                    stats.successes += 1
                    stats.consecutive_failures = 0
                    stats.total_latency_ms += elapsed
                    stats.last_latency_ms = elapsed
                    stats.last_error_code = None
                    stats.last_error_message = None
                    stats.circuit_open_until = 0.0
                return result

        assert final_error is not None
        raise final_error

    def cached_health(
        self,
        provider: str,
        loader: Callable[[], dict[str, Any]],
        *,
        ttl_seconds: float,
    ) -> dict[str, Any]:
        now = monotonic()
        with self._lock:
            cached = self._health_cache.get(provider)
            if cached and cached[0] > now:
                result = dict(cached[1])
                result["cached"] = True
                return result

        result = dict(loader())
        with self._lock:
            self._health_cache[provider] = (now + ttl_seconds, result)
        result["cached"] = False
        return result

    def snapshot(self) -> dict[str, Any]:
        now = monotonic()
        with self._lock:
            return {
                name: stats.snapshot(now)
                for name, stats in sorted(self._stats.items())
            }


provider_runtime = ProviderRuntimeRegistry()
