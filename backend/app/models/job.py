from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


JobStatus = Literal["queued", "processing", "completed", "failed"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRecord(BaseModel):
    job_id: str
    status: JobStatus = "queued"
    provider: str
    message: str = "Job queued."
    person_file: str
    person_files: list[str] = Field(default_factory=list)
    selected_person_index: int | None = None
    validation_report: dict[str, object] = Field(default_factory=dict)
    geometry_profile: dict[str, object] = Field(default_factory=dict)
    geometry_reference_index: int | None = None
    garment_file: str
    garment_description: str = "clothing"
    cloth_type: str = "overall"
    show_type: str = "result only"
    quality_preset: str = "balanced"
    request_parameters: dict[str, int | float] = Field(default_factory=dict)
    provider_metadata: dict[str, object] = Field(default_factory=dict)
    garment_analysis: dict[str, object] = Field(default_factory=dict)
    commercial_instructions: str | None = None
    quality_report: dict[str, object] = Field(default_factory=dict)
    phase3c2_report: dict[str, object] = Field(default_factory=dict)
    retry_history: list[dict[str, object]] = Field(default_factory=list)
    generation_rounds: int = 0
    favorite: bool = False
    notes: str = ""
    downloads: int = 0
    share_token: str | None = None
    deleted_at: str | None = None
    quality_score: float | None = None
    geometry_score: float | None = None
    generation_time_seconds: float | None = None
    endpoint_used: str | None = None
    result_file: str | None = None
    result_url: str | None = None
    error: str | None = None
    error_code: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
