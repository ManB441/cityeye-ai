from pathlib import Path
import sys

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app


client = TestClient(app)


def test_health_endpoint_returns_service_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "cityeye-ai-backend",
    }


def test_health_endpoint_rejects_unsupported_method() -> None:
    response = client.post("/health")

    assert response.status_code == 405


def test_openapi_includes_health_endpoint() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
