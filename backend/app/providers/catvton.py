from __future__ import annotations

from pathlib import Path
from typing import Any

from gradio_client import Client, handle_file

from app.core.config import Settings
from app.providers.base import (
    ProviderConfigurationError,
    ProviderError,
    ProviderUnavailableError,
    TryOnRequest,
    TryOnResult,
    VTONProvider,
)
from app.services.image_normalizer import (
    normalize_for_provider,
)


class CatVTONProvider(VTONProvider):
    name = "catvton"

    SUPPORTED_ENDPOINTS = {
        "/submit_function",
        "/submit_function_flux",
        "/submit_function_p2p",
    }

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings

    def _client(self) -> Client:
        try:
            kwargs: dict[str, Any] = {}

            if self.settings.hf_token:
                kwargs["hf_token"] = (
                    self.settings.hf_token
                )

            return Client(
                self.settings.hf_space,
                **kwargs,
            )

        except Exception as exc:
            raise ProviderUnavailableError(
                (
                    "Could not connect to "
                    f"CatVTON Space "
                    f"'{self.settings.hf_space}': "
                    f"{exc}"
                ),
                provider=self.name,
                details={
                    "space":
                        self.settings.hf_space,
                },
            ) from exc

    @staticmethod
    def _editor_payload(
        path: Path,
    ) -> dict[str, Any]:
        file_value = handle_file(
            str(path)
        )

        return {
            "background": file_value,
            "layers": [],
            "composite": file_value,
        }

    @staticmethod
    def _extract_result(
        result: Any,
        endpoint: str | None = None,
    ) -> TryOnResult:
        candidates: list[Any]

        if isinstance(result, (list, tuple)):
            candidates = list(result)
        else:
            candidates = [result]

        for candidate in candidates:
            if isinstance(candidate, dict):
                path_value = (
                    candidate.get("path")
                    or candidate.get("image")
                    or candidate.get("file")
                )

                url_value = candidate.get("url")

                if path_value or url_value:
                    return TryOnResult(
                        image_path=(
                            Path(path_value)
                            if path_value
                            else None
                        ),
                        image_url=(
                            str(url_value)
                            if url_value
                            else None
                        ),
                        raw=result,
                        endpoint_used=endpoint,
                        metadata={
                            "provider": "catvton",
                        },
                    )

            if isinstance(candidate, str):
                if candidate.startswith(
                    ("http://", "https://")
                ):
                    return TryOnResult(
                        image_url=candidate,
                        raw=result,
                        endpoint_used=endpoint,
                        metadata={
                            "provider": "catvton",
                        },
                    )

                return TryOnResult(
                    image_path=Path(candidate),
                    raw=result,
                    endpoint_used=endpoint,
                    metadata={
                        "provider": "catvton",
                    },
                )

        raise ProviderError(
            (
                "CatVTON returned an unsupported "
                f"result: {type(result).__name__}"
            ),
            code="invalid_provider_response",
            provider="catvton",
            retryable=False,
        )

    @staticmethod
    def _friendly_remote_error(
        exc: Exception,
        endpoint: str,
    ) -> str:
        raw = (
            str(exc).strip()
            or exc.__class__.__name__
        )
        lower = raw.lower()

        if (
            "cannot write mode rgba as jpeg"
            in lower
        ):
            return (
                f"CatVTON endpoint {endpoint} "
                "failed while converting RGBA "
                "to JPEG. Local inputs were "
                "normalized to PNG; this is a "
                "remote Space-side image "
                "conversion error."
            )

        if (
            "zerogpu" in lower
            or "quota" in lower
            or "gpu capacity" in lower
        ):
            return (
                f"CatVTON endpoint {endpoint} "
                "could not obtain free GPU "
                f"capacity. Remote response: "
                f"{raw}"
            )

        if (
            "timeout" in lower
            or "timed out" in lower
            or "connection" in lower
            or "queue" in lower
        ):
            return (
                f"CatVTON endpoint {endpoint} "
                f"is temporarily unavailable: "
                f"{raw}"
            )

        if raw == "RuntimeError":
            return (
                f"CatVTON endpoint {endpoint} "
                "returned an internal "
                "RuntimeError. The Space "
                "accepted the request but its "
                "inference worker failed "
                "without a detailed message."
            )

        return (
            f"CatVTON endpoint {endpoint} "
            f"failed: {raw}"
        )

    @staticmethod
    def _remote_error_to_provider_error(
        exc: Exception,
        endpoint: str,
    ) -> ProviderError:
        message = (
            CatVTONProvider
            ._friendly_remote_error(
                exc,
                endpoint,
            )
        )

        raw = (
            str(exc).strip()
            or exc.__class__.__name__
        )
        lower = raw.lower()

        if (
            "cannot write mode rgba as jpeg"
            in lower
        ):
            return ProviderError(
                message,
                code="catvton_remote_image_error",
                provider="catvton",
                retryable=False,
                details={
                    "endpoint": endpoint,
                    "remote_error": raw,
                },
            )

        if (
            "zerogpu" in lower
            or "quota" in lower
            or "gpu capacity" in lower
            or "timeout" in lower
            or "timed out" in lower
            or "connection" in lower
            or "queue" in lower
        ):
            return ProviderUnavailableError(
                message,
                provider="catvton",
                details={
                    "endpoint": endpoint,
                    "remote_error": raw,
                },
            )

        if raw == "RuntimeError":
            return ProviderError(
                message,
                code="catvton_remote_runtime_error",
                provider="catvton",
                retryable=True,
                details={
                    "endpoint": endpoint,
                },
            )

        return ProviderError(
            message,
            code="catvton_remote_error",
            provider="catvton",
            retryable=True,
            details={
                "endpoint": endpoint,
                "remote_error": raw,
            },
        )

    def _validate_endpoint(
        self,
        endpoint: str,
    ) -> None:
        if endpoint not in self.SUPPORTED_ENDPOINTS:
            raise ProviderError(
                (
                    "Unsupported CatVTON endpoint "
                    f"configured: {endpoint}"
                ),
                code="unsupported_catvton_endpoint",
                provider=self.name,
                retryable=False,
                details={
                    "supported_endpoints": sorted(
                        self.SUPPORTED_ENDPOINTS
                    )
                },
            )

    def _predict(
        self,
        client: Client,
        endpoint: str,
        person_input: Any,
        garment: Path,
        request: TryOnRequest,
    ) -> TryOnResult:
        self._validate_endpoint(endpoint)

        garment_input = handle_file(
            str(garment)
        )

        if endpoint in {
            "/submit_function",
            "/submit_function_flux",
        }:
            result = client.predict(
                person_input,
                garment_input,
                request.cloth_type,
                float(
                    request.num_inference_steps
                ),
                float(request.guidance_scale),
                float(request.seed),
                request.show_type,
                api_name=endpoint,
            )

        else:
            result = client.predict(
                person_input,
                garment_input,
                float(
                    request.num_inference_steps
                ),
                float(request.guidance_scale),
                float(request.seed),
                api_name=endpoint,
            )

        return self._extract_result(
            result,
            endpoint,
        )

    def health(self) -> dict[str, Any]:
        configured = bool(
            self.settings.hf_space
            and self.settings.hf_api_name
        )

        endpoint_valid = (
            self.settings.hf_api_name
            in self.SUPPORTED_ENDPOINTS
        )

        fallback_valid = (
            self.settings.hf_fallback_api_name
            is None
            or self.settings.hf_fallback_api_name
            in self.SUPPORTED_ENDPOINTS
        )

        return {
            "provider": self.name,
            "configured": configured,
            "space": self.settings.hf_space,
            "api_name":
                self.settings.hf_api_name,
            "api_name_valid": endpoint_valid,
            "fallback_api_name":
                self.settings.hf_fallback_api_name,
            "fallback_api_name_valid":
                fallback_valid,
            "fallback_enabled":
                self.settings.hf_enable_fallback,
            "cloth_type":
                self.settings.hf_cloth_type,
            "show_type":
                self.settings.hf_show_type,
            "token_configured":
                bool(self.settings.hf_token),
            "integration_status":
                "phase_4_1_ready",
        }

    def generate(
        self,
        request: TryOnRequest,
    ) -> TryOnResult:
        normalized_dir = (
            self.settings.uploads_dir
            / "normalized"
        )

        person = normalize_for_provider(
            request.person_image,
            normalized_dir,
            output_format="PNG",
        )

        garment = normalize_for_provider(
            request.garment_image,
            normalized_dir,
            output_format="PNG",
        )

        client = self._client()

        if self.settings.hf_input_mode == "editor":
            person_input: Any = (
                self._editor_payload(person)
            )
        else:
            person_input = handle_file(
                str(person)
            )

        endpoints = [
            self.settings.hf_api_name
        ]

        fallback = (
            self.settings.hf_fallback_api_name
        )

        if (
            self.settings.hf_enable_fallback
            and fallback
            and fallback not in endpoints
        ):
            endpoints.append(fallback)

        errors: list[ProviderError] = []

        for endpoint in endpoints:
            try:
                return self._predict(
                    client=client,
                    endpoint=endpoint,
                    person_input=person_input,
                    garment=garment,
                    request=request,
                )

            except ProviderConfigurationError:
                raise

            except ProviderError as exc:
                if exc.code in {
                    "invalid_provider_response",
                    "unsupported_catvton_endpoint",
                }:
                    raise

                errors.append(exc)

            except Exception as exc:
                errors.append(
                    self._remote_error_to_provider_error(
                        exc,
                        endpoint,
                    )
                )

        message = (
            " | ".join(str(error) for error in errors)
            if errors
            else "CatVTON request failed."
        )

        raise ProviderError(
            message,
            code="catvton_request_failed",
            provider=self.name,
            retryable=any(
                error.retryable
                for error in errors
            ),
            details={
                "attempted_endpoints":
                    endpoints,
                "errors": [
                    error.to_dict()
                    for error in errors
                ],
            },
        )