from pathlib import Path
import sys

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app, create_app


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
    assert "/health/live" in response.json()["paths"]
    assert "/health/ready" in response.json()["paths"]


def test_liveness_endpoint_returns_process_status() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_checks_database_and_reports_optional_artifacts(tmp_path: Path) -> None:
    application = create_app(
        database_path=tmp_path / "cityeye.db",
        ai_output_dir=tmp_path / "output",
    )

    with TestClient(application) as test_client:
        response = test_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["components"] == {
        "database": {"status": "ok"},
        "ai_artifacts": {
            "status": "degraded",
            "detail": "Optional AI artifacts missing: tracks.csv, annotated.mp4",
        },
    }
    assert response.headers["X-Request-ID"]


def test_request_id_is_preserved() -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "demo-request"})

    assert response.headers["X-Request-ID"] == "demo-request"
