from __future__ import annotations

import json

import numpy as np

from app.models.job import JobRecord
from app.services.storage import load_job, save_job, to_json_safe


def test_to_json_safe_converts_numpy_scalars_and_arrays() -> None:
    payload = {
        "accepted": np.bool_(True),
        "score": np.float32(0.8841),
        "index": np.int64(2),
        "values": np.array([1, 2, 3], dtype=np.int32),
        "nested": [np.bool_(False)],
    }

    result = to_json_safe(payload)

    assert result["accepted"] is True
    assert isinstance(result["score"], float)
    assert result["index"] == 2
    assert result["values"] == [1, 2, 3]
    assert result["nested"] == [False]
    json.dumps(result)


def test_save_job_persists_numpy_provider_metadata(test_settings) -> None:
    record = JobRecord(
        job_id="numpy-safe-job",
        provider="vertex",
        person_file="person.png",
        person_files=["person.png"],
        garment_file="garment.png",
        provider_metadata={
            "hard_rejected": np.bool_(False),
            "score": np.float64(0.91),
            "selected": np.int32(1),
        },
        validation_report={"accepted": np.bool_(True)},
    )

    save_job(record, test_settings)
    loaded = load_job(record.job_id, test_settings)

    assert loaded is not None
    assert loaded.provider_metadata["hard_rejected"] is False
    assert loaded.provider_metadata["score"] == 0.91
    assert loaded.provider_metadata["selected"] == 1
    assert loaded.validation_report["accepted"] is True
