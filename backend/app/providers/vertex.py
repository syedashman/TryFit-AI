from __future__ import annotations

import base64
import mimetypes
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.providers.base import (
    ProviderConfigurationError,
    ProviderError,
    ProviderUnavailableError,
    TryOnRequest,
    TryOnResult,
    VTONProvider,
)
from app.services.body_geometry import (
    build_body_geometry_profile,
    distortion_penalties,
    geometry_similarity,
)
from app.services.candidate_selector import (
    choose_best_candidate,
)
from app.services.image_normalizer import (
    normalize_for_provider,
)


class VertexTryOnProvider(VTONProvider):
    name = "vertex"

    scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
    ]

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _missing_settings(self) -> list[str]:
        required = {
            "GOOGLE_CLOUD_PROJECT":
                self.settings.google_cloud_project,
            "VERTEX_MODEL":
                self.settings.vertex_model,
        }

        return [
            name
            for name, value in required.items()
            if not value
        ]

    @property
    def predict_url(self) -> str:
        project = self.settings.google_cloud_project
        location = self.settings.google_cloud_location
        model = self.settings.vertex_model

        return (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project}/locations/{location}/"
            f"publishers/google/models/{model}:predict"
        )

    def health(self) -> dict[str, Any]:
        missing = self._missing_settings()
        credentials_path = (
            self.settings.google_application_credentials
        )

        return {
            "provider": self.name,
            "configured": not missing,
            "project":
                self.settings.google_cloud_project,
            "location":
                self.settings.google_cloud_location,
            "model":
                self.settings.vertex_model,
            "sample_count":
                self.settings.vertex_sample_count,
            "candidate_count":
                self.settings.vertex_candidate_count,
            "geometry_selection_enabled":
                self.settings.geometry_selection_enabled,
            "storage_uri":
                self.settings.vertex_storage_uri,
            "credentials_file_configured":
                bool(credentials_path),
            "credentials_file_exists": bool(
                credentials_path
                and Path(credentials_path).exists()
            ),
            "adc_supported": True,
            "missing_settings": missing,
            "implementation_status":
                "production_rest_integration",
            "max_retries":
                self.settings.vertex_max_retries,
            "commercial_quality_threshold":
                self.settings.commercial_quality_threshold,
            "commercial_max_generation_rounds":
                self.settings
                .commercial_max_generation_rounds,
        }

    def _configure_credentials_path(self) -> None:
        path = (
            self.settings.google_application_credentials
        )

        if not path:
            return

        resolved = str(
            Path(path).expanduser().resolve()
        )

        if not Path(resolved).exists():
            raise ProviderConfigurationError(
                "Google credentials file does not exist: "
                f"{resolved}"
            )

        os.environ[
            "GOOGLE_APPLICATION_CREDENTIALS"
        ] = resolved

    def _access_token(self) -> str:
        self._configure_credentials_path()

        try:
            import google.auth
            from google.auth.transport.requests import (
                Request as GoogleAuthRequest,
            )

            credentials, detected_project = (
                google.auth.default(
                    scopes=self.scopes
                )
            )

            if (
                not self.settings.google_cloud_project
                and detected_project
            ):
                self.settings.google_cloud_project = (
                    detected_project
                )

            credentials.refresh(
                GoogleAuthRequest()
            )

            token = getattr(
                credentials,
                "token",
                None,
            )

            if not token:
                raise RuntimeError(
                    "Google authentication returned "
                    "no access token."
                )

            return token

        except ProviderError:
            raise

        except Exception as exc:
            raise ProviderConfigurationError(
                "Google authentication failed. Run "
                "'gcloud auth application-default login' "
                "or configure GOOGLE_APPLICATION_CREDENTIALS "
                "with a service-account JSON file. "
                f"Original error: {exc}"
            ) from exc

    @staticmethod
    def _encode_image(path: Path) -> str:
        return base64.b64encode(
            path.read_bytes()
        ).decode("ascii")

    def _build_payload(
        self,
        person_image: Path,
        garment_image: Path,
        sample_count: int,
    ) -> dict[str, Any]:
        parameters: dict[str, Any] = {
            "sampleCount": int(sample_count),
            # Vertex Virtual Try-On may block person editing unless the
            # permitted age category is explicitly supplied.
            "personGeneration": "allow-all",
        }

        if self.settings.vertex_storage_uri:
            parameters["storageUri"] = (
                self.settings.vertex_storage_uri
            )

        return {
            "instances": [
                {
                    "personImage": {
                        "image": {
                            "bytesBase64Encoded":
                                self._encode_image(
                                    person_image
                                )
                        }
                    },
                    "productImages": [
                        {
                            "image": {
                                "bytesBase64Encoded":
                                    self._encode_image(
                                        garment_image
                                    )
                            }
                        }
                    ],
                }
            ],
            "parameters": parameters,
        }

    @staticmethod
    def _friendly_http_error(
        response: httpx.Response,
    ) -> ProviderError:
        try:
            body = response.json()

        except ValueError:
            body = response.text

        detail = body

        if isinstance(body, dict):
            error = body.get("error")

            if isinstance(error, dict):
                detail = (
                    error.get("message")
                    or error
                )

        if response.status_code in {401, 403}:
            return ProviderConfigurationError(
                "Vertex authentication or IAM access "
                f"failed ({response.status_code}): "
                f"{detail}"
            )

        if response.status_code == 404:
            return ProviderConfigurationError(
                "Vertex model or project endpoint was "
                "not found. Check GOOGLE_CLOUD_PROJECT, "
                "GOOGLE_CLOUD_LOCATION, API enablement "
                "and VERTEX_MODEL. "
                f"Remote detail: {detail}"
            )

        if response.status_code == 429:
            return ProviderUnavailableError(
                "Vertex quota or capacity limit reached: "
                f"{detail}"
            )

        detail_text = str(detail)
        detail_lower = detail_text.lower()

        if (
            response.status_code == 400
            and (
                "person generation" in detail_lower
                or "allow (adults only)" in detail_lower
                or "17301594" in detail_lower
            )
        ):
            return ProviderError(
                (
                    "This photo couldn't be processed because Google's safety "
                    "system flagged it (this can happen with blurry, filtered, "
                    "or unusual-looking selfies). Please try a different, clear "
                    "photo for this slot. "
                    f"Technical detail: {detail_text}"
                ),
                code="vertex_person_generation_blocked",
                provider="vertex",
                retryable=False,
                details={
                    "status_code": response.status_code,
                    "support_code": "17301594",
                    "remote_error": detail_text,
                },
            )

        if response.status_code >= 500:
            return ProviderUnavailableError(
                "Vertex service failed "
                f"({response.status_code}): {detail}"
            )

        return ProviderError(
            "Vertex request failed "
            f"({response.status_code}): {detail}",
            code="vertex_request_failed",
        )

    @staticmethod
    def _decode_prediction(
        prediction: dict[str, Any],
        output_path: Path,
    ) -> Path:
        encoded = prediction.get(
            "bytesBase64Encoded"
        )

        if not encoded:
            raise ProviderError(
                "Vertex response did not contain "
                "bytesBase64Encoded.",
                code="invalid_vertex_response",
            )

        mime_type = prediction.get(
            "mimeType",
            "image/png",
        )

        extension = (
            mimetypes.guess_extension(mime_type)
            or ".png"
        )

        final_path = output_path.with_suffix(
            extension
        )

        try:
            final_path.write_bytes(
                base64.b64decode(
                    encoded,
                    validate=True,
                )
            )

        except Exception as exc:
            raise ProviderError(
                "Vertex returned invalid base64 "
                f"image data: {exc}",
                code="invalid_vertex_response",
            ) from exc

        return final_path

    @staticmethod
    def _single_candidate_rejected(
        penalties: dict[str, float],
    ) -> bool:
        canvas_changed = (
            penalties.get(
                "canvas_aspect_change",
                0.0,
            )
            > 0.20
        )

        compressed_and_wide = (
            penalties.get(
                "height_compression",
                0.0,
            )
            > 0.24
            and penalties.get(
                "body_widening",
                0.0,
            )
            > 0.12
        )

        extreme_compression = (
            penalties.get(
                "height_compression",
                0.0,
            )
            > 0.38
        )

        extreme_widening = (
            penalties.get(
                "body_widening",
                0.0,
            )
            > 0.32
        )

        return bool(
            canvas_changed
            or compressed_and_wide
            or extreme_compression
            or extreme_widening
        )

    def generate(
        self,
        request: TryOnRequest,
    ) -> TryOnResult:
        missing = self._missing_settings()

        if missing:
            raise ProviderConfigurationError(
                "Vertex provider is selected but "
                "these settings are missing: "
                + ", ".join(missing)
            )

        normalized_dir = (
            self.settings.uploads_dir
            / "normalized"
        )

        # Redundant provider-level protection:
        # even if an older job_service passes the face image,
        # overall/lower garments use geometry_reference_image.
        render_source = request.person_image

        if (
            request.cloth_type in {"overall", "lower"}
            and request.geometry_reference_image
            is not None
            and request.geometry_reference_image.exists()
        ):
            render_source = (
                request.geometry_reference_image
            )

        person = normalize_for_provider(
            render_source,
            normalized_dir,
            output_format="PNG",
        )

        garment = normalize_for_provider(
            request.garment_image,
            normalized_dir,
            output_format="PNG",
        )

        token = self._access_token()

        candidate_count = (
            self.settings.vertex_candidate_count
            if self.settings
            .geometry_selection_enabled
            else self.settings.vertex_sample_count
        )

        payload = self._build_payload(
            person,
            garment,
            candidate_count,
        )

        response: httpx.Response | None = None
        attempts = (
            self.settings.vertex_max_retries
            + 1
        )

        for attempt in range(attempts):
            try:
                with httpx.Client(
                    timeout=(
                        self.settings
                        .vertex_request_timeout_seconds
                    )
                ) as client:
                    
                    # Safe payload logging: structure and sizes only — never
                    # the base64 image bytes or the bearer token. This lets a
                    # request be triaged from logs without leaking credentials
                    # or huge blobs.
                    instances = payload.get("instances", [])
                    instance_shape = []
                    for inst in instances:
                        person_b64 = (
                            inst.get("personImage", {})
                            .get("image", {})
                            .get("bytesBase64Encoded", "")
                        )
                        products = inst.get("productImages", [])
                        product_sizes = [
                            len(
                                p.get("image", {}).get(
                                    "bytesBase64Encoded", ""
                                )
                            )
                            for p in products
                        ]
                        instance_shape.append(
                            {
                                "personImage_b64_len": len(person_b64),
                                "productImages_count": len(products),
                                "productImage_b64_lens": product_sizes,
                            }
                        )
                    print(
                        "VERTEX PAYLOAD SHAPE:",
                        {
                            "top_level_keys": sorted(payload.keys()),
                            "instances": instance_shape,
                            "parameters": payload.get("parameters"),
                        },
                    )
                    response = client.post(
                        self.predict_url,
                        headers={
                            "Authorization":
                                f"Bearer {token}",
                            "Content-Type":
                                "application/json; "
                                "charset=utf-8",
                            "X-TryFit-Request":
                                "sprint-4-phase-3a",
                        },
                        json=payload,
                    )

            except (
                httpx.TimeoutException,
                httpx.TransportError,
            ) as exc:
                if attempt >= attempts - 1:
                    raise ProviderUnavailableError(
                        "Vertex Virtual Try-On could "
                        "not be reached after "
                        f"{attempts} attempts: {exc}"
                    ) from exc

                time.sleep(
                    self.settings
                    .vertex_retry_backoff_seconds
                    * (2**attempt)
                )

                continue

            if response.status_code < 400:
                break

            retryable = response.status_code in {
                429,
                500,
                502,
                503,
                504,
            }

            if (
                not retryable
                or attempt >= attempts - 1
            ):
                raise self._friendly_http_error(
                    response
                )

            time.sleep(
                self.settings
                .vertex_retry_backoff_seconds
                * (2**attempt)
            )

        if response is None:
            raise ProviderUnavailableError(
                "Vertex Virtual Try-On returned "
                "no response."
            )

        try:
            data = response.json()

        except ValueError as exc:
            raise ProviderError(
                "Vertex returned a non-JSON response.",
                code="invalid_vertex_response",
            ) from exc

        predictions = data.get("predictions")

        if (
            not isinstance(predictions, list)
            or not predictions
        ):
            raise ProviderError(
                "Vertex returned no predictions: "
                f"{data}",
                code="invalid_vertex_response",
            )

        self.settings.results_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        generation_id = uuid.uuid4().hex

        candidate_paths: list[Path] = []

        for index, prediction in enumerate(
            predictions
        ):
            temp_output = (
                self.settings.results_dir
                / (
                    f"vertex-{generation_id}"
                    f"-candidate-{index}"
                )
            )

            candidate_paths.append(
                self._decode_prediction(
                    prediction,
                    temp_output,
                )
            )

        # Use exact normalized image sent to Vertex.
        render_reference_profile = (
            build_body_geometry_profile(person)
        )

        full_body_reference_path = (
            request.geometry_reference_image
            or render_source
        )

        full_body_reference = (
            normalize_for_provider(
                full_body_reference_path,
                normalized_dir,
                output_format="PNG",
            )
        )

        full_body_reference_profile = (
            build_body_geometry_profile(
                full_body_reference
            )
        )

        chosen_path = candidate_paths[0]
        candidate_scores: list[
            dict[str, Any]
        ] = []

        if (
            self.settings.geometry_selection_enabled
            and len(candidate_paths) > 1
        ):
            chosen_path, scores = (
                choose_best_candidate(
                    candidate_paths,
                    render_reference_profile,
                    full_body_reference_profile,
                    garment_reference_path=request.garment_image,
                )
            )

            candidate_scores = [
                item.to_dict()
                for item in scores
            ]

            # Per-candidate diagnostic logging. This is intentionally verbose
            # so a rejected batch can be triaged from logs alone.
            print("PERSON USED:", str(person))
            for s in scores:
                print(
                    "CANDIDATE",
                    {
                        "index": s.index,
                        "geometry": round(
                            s.geometry_similarity, 3
                        ),
                        "full_body": round(
                            s.full_body_similarity, 3
                        ),
                        "color": round(
                            s.garment_color_score, 3
                        ),
                        "structure": round(
                            s.garment_structure_score, 3
                        ),
                        "length": round(
                            s.garment_length_score, 3
                        ),
                        "long_violation":
                            s.long_garment_violation,
                        "long_garment_confidence":
                            s.long_garment_confidence,
                        "final": s.final_score,
                        "hard_rejected": s.hard_rejected,
                        "rejection_reasons": list(
                            s.rejection_reasons or []
                        ),
                    },
                )
            print(
                "CHOSEN CANDIDATE:",
                Path(chosen_path).name,
            )

        else:
            candidate_profile = (
                build_body_geometry_profile(
                    chosen_path
                )
            )

            single_similarity = (
                geometry_similarity(
                    render_reference_profile,
                    candidate_profile,
                )
            )

            full_body_similarity = (
                geometry_similarity(
                    full_body_reference_profile,
                    candidate_profile,
                )
            )

            penalties = (
                distortion_penalties(
                    render_reference_profile,
                    candidate_profile,
                )
            )

            hard_rejected = (
                self._single_candidate_rejected(
                    penalties
                )
            )

            candidate_scores = [
                {
                    "index": 0,
                    "path": str(chosen_path),
                    "geometry_similarity":
                        float(single_similarity),
                    "full_body_similarity":
                        float(full_body_similarity),
                    "final_score":
                        float(single_similarity),
                    "hard_rejected":
                        bool(hard_rejected),
                    "penalties": {
                        key: float(value)
                        for key, value
                        in penalties.items()
                    },
                    "candidate_profile":
                        candidate_profile.to_dict(),
                }
            ]

        chosen_index = candidate_paths.index(
            chosen_path
        )

        selected_score = next(
            (
                item
                for item in candidate_scores
                if item.get("index")
                == chosen_index
            ),
            (
                candidate_scores[0]
                if candidate_scores
                else {}
            ),
        )

        if (
            self.settings
            .commercial_reject_distorted_results
            and bool(
                selected_score.get(
                    "hard_rejected"
                )
            )
        ):
            # Distinguish the dominant failure class so the caller can decide
            # whether a same-photo generation retry is worthwhile. Garment
            # fidelity failures (wrong color/structure/length, or a long
            # garment rendered short) are reported as garment_fidelity_failed;
            # body geometry distortion is reported as distorted_tryon_result.
            selected_reasons = list(
                selected_score.get(
                    "rejection_reasons"
                )
                or []
            )

            garment_reasons = {
                "garment_color_mismatch",
                "garment_structure_mismatch",
                "garment_length_mismatch",
                "long_garment_shortened",
            }

            has_garment_failure = any(
                reason in garment_reasons
                for reason in selected_reasons
            )
            has_geometry_failure = (
                "geometry_distortion"
                in selected_reasons
            )

            if (
                has_garment_failure
                and not has_geometry_failure
            ):
                raise ProviderError(
                    "Vertex could not preserve the "
                    "garment's color, structure, or "
                    "length on any candidate. The "
                    "generated try-on does not match "
                    "the reference outfit.",
                    code="garment_fidelity_failed",
                    provider="vertex",
                    retryable=True,
                    details={
                        "rejection_reasons":
                            selected_reasons,
                    },
                )

            raise ProviderError(
                "Vertex generated only "
                "body-distorted candidates. "
                "Please retry with a clear "
                "full-body photo where the "
                "complete person, including "
                "feet, is visible.",
                code="distorted_tryon_result",
                provider="vertex",
                retryable=True,
                details={
                    "rejection_reasons":
                        selected_reasons,
                },
            )

        return TryOnResult(
            image_path=chosen_path,
            raw={
                "prediction_count":
                    int(len(predictions)),
                "model":
                    self.settings.vertex_model,
                "location":
                    self.settings
                    .google_cloud_location,
                "sample_count":
                    int(candidate_count),
                "geometry_selection_enabled":
                    bool(
                        self.settings
                        .geometry_selection_enabled
                    ),
                "render_input_file":
                    str(render_source),
                "normalized_render_input":
                    str(person),
                "render_reference":
                    render_reference_profile.to_dict(),
                "full_body_reference":
                    full_body_reference_profile
                    .to_dict(),
                "candidate_scores":
                    candidate_scores,
                "selected_candidate_index":
                    int(chosen_index),
                "selected_geometry_similarity":
                    selected_score.get(
                        "geometry_similarity"
                    ),
                "selected_final_geometry_score":
                    selected_score.get(
                        "final_score"
                    ),
                "generation_rounds": 1,
                "commercial_quality_threshold":
                    float(
                        self.settings
                        .commercial_quality_threshold
                    ),
                "commercial_instructions":
                    request
                    .commercial_instructions,
                "commercial_retry_note":
                    "One generation round requests "
                    "multiple official Vertex "
                    "candidates.",
                "seed_note":
                    "Vertex Virtual Try-On REST "
                    "does not expose seed control; "
                    "diversity is requested through "
                    "sampleCount.",
                "request_parameters": {
                    "num_inference_steps":
                        int(
                            request
                            .num_inference_steps
                        ),
                    "guidance_scale":
                        float(
                            request
                            .guidance_scale
                        ),
                    "seed":
                        int(request.seed),
                },
            },
            endpoint_used=(
                self.settings.vertex_model
            ),
        )