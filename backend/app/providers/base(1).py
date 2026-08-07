from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TryOnRequest:
    person_image: Path
    garment_image: Path
    garment_description: str = "clothing"
    cloth_type: str = "overall"
    show_type: str = "result only"
    num_inference_steps: int = 50
    guidance_scale: float = 2.5
    seed: int = 42
    person_images: list[Path] | None = None
    geometry_reference_image: Path | None = None
    geometry_profile: dict[str, Any] | None = None
    commercial_instructions: str | None = None

    def __post_init__(self) -> None:
        self.person_image = Path(
            self.person_image
        )
        self.garment_image = Path(
            self.garment_image
        )

        if self.person_images is not None:
            self.person_images = [
                Path(path)
                for path in self.person_images
            ]

        if (
            self.geometry_reference_image
            is not None
        ):
            self.geometry_reference_image = Path(
                self.geometry_reference_image
            )

        self.garment_description = (
            self.garment_description.strip()
            or "clothing"
        )

        self.cloth_type = (
            self.cloth_type.strip().lower()
        )

        self.show_type = (
            self.show_type.strip().lower()
        )

        if self.cloth_type not in {
            "upper",
            "lower",
            "overall",
        }:
            raise ValueError(
                "cloth_type must be upper, "
                "lower, or overall."
            )

        if self.num_inference_steps < 1:
            raise ValueError(
                "num_inference_steps must "
                "be greater than zero."
            )

        if self.guidance_scale < 0:
            raise ValueError(
                "guidance_scale cannot "
                "be negative."
            )

    def all_person_images(self) -> list[Path]:
        """Return every supplied person image without duplicates."""
        images = [
            self.person_image
        ]

        if self.person_images:
            images.extend(
                self.person_images
            )

        unique: list[Path] = []
        seen: set[str] = set()

        for path in images:
            key = str(
                path.expanduser()
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(path)

        return unique


@dataclass(slots=True)
class TryOnResult:
    image_path: Path | None = None
    image_url: str | None = None
    raw: Any = None
    endpoint_used: str | None = None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.image_path is not None:
            self.image_path = Path(
                self.image_path
            )

        if (
            self.image_path is None
            and not self.image_url
        ):
            raise ValueError(
                "TryOnResult requires either "
                "image_path or image_url."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_path": (
                str(self.image_path)
                if self.image_path
                is not None
                else None
            ),
            "image_url": self.image_url,
            "raw": self.raw,
            "endpoint_used":
                self.endpoint_used,
            "metadata": self.metadata,
        }


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        code: str = "provider_error",
        *,
        provider: str | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)

        self.code = code
        self.provider = provider
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "code": self.code,
            "provider": self.provider,
            "retryable": self.retryable,
            "details": self.details,
        }


class ProviderConfigurationError(
    ProviderError
):
    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=(
                "provider_configuration_error"
            ),
            provider=provider,
            retryable=False,
            details=details,
        )


class ProviderUnavailableError(
    ProviderError
):
    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="provider_unavailable",
            provider=provider,
            retryable=True,
            details=details,
        )


class VTONProvider(ABC):
    name: str

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return provider configuration and availability information."""
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        request: TryOnRequest,
    ) -> TryOnResult:
        """Generate one virtual try-on result."""
        raise NotImplementedError