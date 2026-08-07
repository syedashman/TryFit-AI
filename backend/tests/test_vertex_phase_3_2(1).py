import base64
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.config import Settings
from app.providers.base import (
    ProviderConfigurationError,
    ProviderUnavailableError,
)
from app.providers.vertex import VertexTryOnProvider


def settings(**kwargs):
    return Settings(
        _env_file=None,
        google_cloud_project="demo-project",
        google_cloud_location="us-central1",
        vertex_model="virtual-try-on-001",
        **kwargs,
    )


def test_vertex_predict_url():
    provider = VertexTryOnProvider(settings())
    assert provider.predict_url == (
        "https://us-central1-aiplatform.googleapis.com/v1/"
        "projects/demo-project/locations/us-central1/publishers/google/"
        "models/virtual-try-on-001:predict"
    )


def test_vertex_payload_matches_official_schema(tmp_path):
    person = tmp_path / "person.png"
    garment = tmp_path / "garment.png"
    person.write_bytes(b"person")
    garment.write_bytes(b"garment")

    provider = VertexTryOnProvider(settings(vertex_sample_count=2))
    payload = provider._build_payload(person, garment, 2)

    assert payload["parameters"]["sampleCount"] == 2
    instance = payload["instances"][0]
    assert base64.b64decode(
        instance["personImage"]["image"]["bytesBase64Encoded"]
    ) == b"person"
    assert base64.b64decode(
        instance["productImages"][0]["image"]["bytesBase64Encoded"]
    ) == b"garment"


def test_vertex_payload_adds_storage_uri(tmp_path):
    person = tmp_path / "person.png"
    garment = tmp_path / "garment.png"
    person.write_bytes(b"person")
    garment.write_bytes(b"garment")

    provider = VertexTryOnProvider(
        settings(vertex_storage_uri="gs://bucket/results/")
    )
    payload = provider._build_payload(person, garment, 1)
    assert payload["parameters"]["storageUri"] == "gs://bucket/results/"


def test_vertex_decodes_prediction(tmp_path):
    encoded = base64.b64encode(b"png-data").decode()
    result = VertexTryOnProvider._decode_prediction(
        {"mimeType": "image/png", "bytesBase64Encoded": encoded},
        tmp_path / "output",
    )
    assert result.read_bytes() == b"png-data"
    assert result.suffix == ".png"


def test_vertex_403_is_configuration_error():
    response = Mock()
    response.status_code = 403
    response.json.return_value = {"error": {"message": "permission denied"}}
    error = VertexTryOnProvider._friendly_http_error(response)
    assert isinstance(error, ProviderConfigurationError)


def test_vertex_429_is_unavailable_error():
    response = Mock()
    response.status_code = 429
    response.json.return_value = {"error": {"message": "quota"}}
    error = VertexTryOnProvider._friendly_http_error(response)
    assert isinstance(error, ProviderUnavailableError)
