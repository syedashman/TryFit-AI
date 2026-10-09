from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["sprint"] == "4"
    assert payload["phase"] == "3A"


def test_netlify_deploy_preview_cors_origin_is_allowed():
    origin = "https://deploy-preview-123--tryfit.netlify.app"
    with TestClient(app) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
