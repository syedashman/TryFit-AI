from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    app_name: str = "TryFit AI"
    app_env: str = "development"
    api_prefix: str = "/api"

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    allowed_image_types: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
        ]
    )

    max_image_size_mb: int = 15
    storage_dir: Path = Path("storage")

    min_person_images: int = 3
    max_person_images: int = 5
    person_min_width: int = 400
    person_min_height: int = 500
    person_min_sharpness: float = 35.0
    identity_consistency_threshold: float = 0.80
    identity_hard_reject_threshold: float = 0.55

    # catvton | vertex | auto
    vton_provider: str = "auto"

    provider_fallback_order: list[str] = Field(
        default_factory=lambda: [
            "vertex",
            "catvton",
        ]
    )

    # Sprint 4 Phase 1 provider runtime controls.
    provider_runtime_max_retries: int = 1
    provider_runtime_backoff_seconds: float = 0.25
    provider_failure_threshold: int = 3
    provider_circuit_cooldown_seconds: float = 30.0
    provider_health_cache_ttl_seconds: float = 15.0

    hf_space: str = "zhengchong/CatVTON"
    hf_api_name: str = "/submit_function"
    hf_fallback_api_name: str | None = (
        "/submit_function_p2p"
    )
    hf_token: str | None = None
    hf_input_mode: str = "editor"
    hf_cloth_type: str = "overall"
    hf_show_type: str = "result only"
    hf_num_inference_steps: int = 50

    # Which backend generate_posed_reference() uses for the side/back pose
    # step: "gemini" (default, uses gemini-2.5-flash-image) or "instantid"
    # (free HF Space, InsightFace-based — non-commercial research license,
    # fine for demos, revisit before commercial launch).
    pose_provider: str = "gemini"
    instantid_space: str = "InstantX/InstantID"
    hf_guidance_scale: float = 2.5
    hf_seed: int = 42
    hf_enable_fallback: bool = True

    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    google_application_credentials: str | None = None

    vertex_model: str = "virtual-try-on-001"
    vertex_sample_count: int = 1
    vertex_storage_uri: str | None = None
    vertex_request_timeout_seconds: float = 180.0
    vertex_max_retries: int = 2
    vertex_retry_backoff_seconds: float = 1.0
    vertex_candidate_count: int = 3
    geometry_selection_enabled: bool = True
    full_body_priority: bool = True
    dual_reference_enabled: bool = True

    # Sprint 3.3 Phase 4 commercial controls.
    commercial_api_enabled: bool = True
    commercial_quality_threshold: float = 0.86
    commercial_max_generation_rounds: int = 2
    commercial_reject_distorted_results: bool = True
    phase3c2_retry_distorted_results: bool = True
    phase3c2_alternate_person_retries: int = 2
    phase3c2_duplicate_similarity_threshold: float = 0.94
    phase3c2_product_color_warning_threshold: float = 0.45

    # Sprint 4 Phase 2 conservative visual-quality refinement.
    visual_enhancement_enabled: bool = True
    visual_enhancement_sharpness: float = 1.08
    visual_enhancement_contrast: float = 1.03
    visual_enhancement_color: float = 1.01

    @field_validator(
        "provider_runtime_max_retries",
        "provider_failure_threshold",
    )
    @classmethod
    def validate_non_negative_runtime_integers(
        cls,
        value: int,
    ) -> int:
        if value < 0:
            raise ValueError("Provider runtime integer settings cannot be negative.")
        return value

    @field_validator(
        "provider_runtime_backoff_seconds",
        "provider_circuit_cooldown_seconds",
        "provider_health_cache_ttl_seconds",
    )
    @classmethod
    def validate_non_negative_runtime_seconds(
        cls,
        value: float,
    ) -> float:
        if value < 0:
            raise ValueError("Provider runtime timing settings cannot be negative.")
        return value

    @field_validator(
        "visual_enhancement_sharpness",
        "visual_enhancement_contrast",
        "visual_enhancement_color",
    )
    @classmethod
    def validate_visual_enhancement_factors(
        cls,
        value: float,
    ) -> float:
        if not 0.5 <= value <= 2.0:
            raise ValueError(
                "Visual enhancement factors must be between 0.5 and 2.0."
            )
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator(
        "cors_origins",
        "allowed_image_types",
        "provider_fallback_order",
        mode="before",
    )
    @classmethod
    def parse_list_value(
        cls,
        value: Any,
    ) -> Any:
        if isinstance(value, list):
            return value

        if isinstance(value, tuple):
            return list(value)

        if isinstance(value, str):
            raw = value.strip()

            if not raw:
                return []

            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)

                except json.JSONDecodeError:
                    parsed = None

                if isinstance(parsed, list):
                    return parsed

            return [
                item.strip()
                for item in raw.split(",")
                if item.strip()
            ]

        return value

    @field_validator(
        "hf_token",
        "hf_fallback_api_name",
        "google_cloud_project",
        "google_application_credentials",
        "vertex_storage_uri",
        mode="before",
    )
    @classmethod
    def blank_string_to_none(
        cls,
        value: Any,
    ) -> Any:
        if (
            isinstance(value, str)
            and not value.strip()
        ):
            return None

        return value

    @field_validator(
        "storage_dir",
        mode="before",
    )
    @classmethod
    def normalize_storage_dir(
        cls,
        value: Any,
    ) -> Any:
        if isinstance(value, str):
            value = value.strip()

        if not value:
            return Path("storage")

        return Path(value).expanduser()

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            return "/api"

        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

        if (
            len(normalized) > 1
            and normalized.endswith("/")
        ):
            normalized = normalized.rstrip("/")

        return normalized

    @field_validator("vton_provider")
    @classmethod
    def normalize_provider(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if normalized not in {
            "catvton",
            "vertex",
            "auto",
        }:
            raise ValueError(
                "VTON_PROVIDER must be "
                "catvton, vertex, or auto."
            )

        return normalized

    @field_validator(
        "provider_fallback_order"
    )
    @classmethod
    def validate_fallback_order(
        cls,
        value: list[str],
    ) -> list[str]:
        normalized = [
            item.strip().lower()
            for item in value
            if item and item.strip()
        ]

        invalid = [
            item
            for item in normalized
            if item
            not in {
                "vertex",
                "catvton",
            }
        ]

        if invalid:
            raise ValueError(
                "PROVIDER_FALLBACK_ORDER only "
                "supports vertex and catvton."
            )

        if not normalized:
            raise ValueError(
                "PROVIDER_FALLBACK_ORDER "
                "cannot be empty."
            )

        return list(
            dict.fromkeys(normalized)
        )

    @field_validator(
        "allowed_image_types"
    )
    @classmethod
    def validate_allowed_image_types(
        cls,
        value: list[str],
    ) -> list[str]:
        normalized = [
            item.strip().lower()
            for item in value
            if item and item.strip()
        ]

        if not normalized:
            raise ValueError(
                "ALLOWED_IMAGE_TYPES "
                "cannot be empty."
            )

        invalid = [
            item
            for item in normalized
            if not item.startswith("image/")
        ]

        if invalid:
            raise ValueError(
                "ALLOWED_IMAGE_TYPES must "
                "contain valid image MIME types."
            )

        return list(
            dict.fromkeys(normalized)
        )

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(
        cls,
        value: list[str],
    ) -> list[str]:
        normalized = [
            item.strip().rstrip("/")
            for item in value
            if item and item.strip()
        ]

        if not normalized:
            raise ValueError(
                "CORS_ORIGINS cannot be empty."
            )

        return list(
            dict.fromkeys(normalized)
        )

    @field_validator("hf_cloth_type")
    @classmethod
    def validate_cloth_type(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if normalized not in {
            "upper",
            "lower",
            "overall",
        }:
            raise ValueError(
                "HF_CLOTH_TYPE must be "
                "upper, lower, or overall."
            )

        return normalized

    @field_validator("hf_show_type")
    @classmethod
    def validate_show_type(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        allowed = {
            "result only",
            "input & result",
            "input & mask & result",
        }

        if normalized not in allowed:
            raise ValueError(
                "HF_SHOW_TYPE must be "
                "'result only', "
                "'input & result', or "
                "'input & mask & result'."
            )

        return normalized

    @field_validator(
        "google_cloud_location",
        "vertex_model",
        "hf_space",
        "hf_api_name",
    )
    @classmethod
    def validate_required_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Configured service values "
                "cannot be blank."
            )

        return normalized

    @field_validator(
        "commercial_quality_threshold"
    )
    @classmethod
    def validate_commercial_quality_threshold(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                "COMMERCIAL_QUALITY_THRESHOLD "
                "must be between 0 and 1."
            )

        return value

    @field_validator(
        "commercial_max_generation_rounds"
    )
    @classmethod
    def validate_commercial_rounds(
        cls,
        value: int,
    ) -> int:
        if not 1 <= value <= 3:
            raise ValueError(
                "COMMERCIAL_MAX_GENERATION_ROUNDS "
                "must be between 1 and 3."
            )

        return value

    @field_validator(
        "vertex_sample_count",
        "vertex_candidate_count",
    )
    @classmethod
    def validate_vertex_sample_count(
        cls,
        value: int,
    ) -> int:
        if not 1 <= value <= 4:
            raise ValueError(
                "Vertex sample/candidate count "
                "must be between 1 and 4."
            )

        return value

    @field_validator(
        "min_person_images",
        "max_person_images",
    )
    @classmethod
    def validate_person_image_limits(
        cls,
        value: int,
    ) -> int:
        if not 1 <= value <= 10:
            raise ValueError(
                "Person image limits must "
                "be between 1 and 10."
            )

        return value

    @field_validator(
        "identity_consistency_threshold",
        "identity_hard_reject_threshold",
    )
    @classmethod
    def validate_identity_threshold(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                "Identity thresholds must "
                "be between 0 and 1."
            )

        return value

    @field_validator(
        "max_image_size_mb",
        "person_min_width",
        "person_min_height",
        "hf_num_inference_steps",
    )
    @classmethod
    def validate_positive_integer(
        cls,
        value: int,
    ) -> int:
        if value < 1:
            raise ValueError(
                "Configured integer values "
                "must be greater than zero."
            )

        return value

    @field_validator(
        "person_min_sharpness",
        "hf_guidance_scale",
        "vertex_request_timeout_seconds",
        "vertex_retry_backoff_seconds",
    )
    @classmethod
    def validate_non_negative_float(
        cls,
        value: float,
    ) -> float:
        if value < 0:
            raise ValueError(
                "Configured numeric values "
                "cannot be negative."
            )

        return value

    @field_validator("vertex_max_retries")
    @classmethod
    def validate_vertex_retries(
        cls,
        value: int,
    ) -> int:
        if not 0 <= value <= 10:
            raise ValueError(
                "VERTEX_MAX_RETRIES must "
                "be between 0 and 10."
            )

        return value

    @model_validator(mode="after")
    def validate_cross_field_settings(
        self,
    ) -> "Settings":
        if (
            self.min_person_images
            > self.max_person_images
        ):
            raise ValueError(
                "MIN_PERSON_IMAGES cannot be "
                "greater than MAX_PERSON_IMAGES."
            )

        if (
            self.identity_hard_reject_threshold
            > self.identity_consistency_threshold
        ):
            raise ValueError(
                "IDENTITY_HARD_REJECT_THRESHOLD "
                "cannot be greater than "
                "IDENTITY_CONSISTENCY_THRESHOLD."
            )

        return self

    def quality_preset(
        self,
        name: str,
    ) -> dict[str, int | float]:
        normalized = name.strip().lower()

        presets: dict[
            str,
            dict[str, int | float],
        ] = {
            "fast": {
                "num_inference_steps": 30,
                "guidance_scale": 2.0,
            },
            "balanced": {
                "num_inference_steps": 50,
                "guidance_scale": 2.5,
            },
            "high": {
                "num_inference_steps": 70,
                "guidance_scale": 3.0,
            },
        }

        try:
            return presets[normalized]

        except KeyError as exc:
            raise ValueError(
                "Unknown quality preset. "
                "Use fast, balanced, or high."
            ) from exc

    @property
    def jobs_dir(self) -> Path:
        return self.storage_dir / "jobs"

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def results_dir(self) -> Path:
        return self.storage_dir / "results"


@lru_cache
def get_settings() -> Settings:
    return Settings()