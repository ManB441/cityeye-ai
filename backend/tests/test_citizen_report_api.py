from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app


def report_payload(demo_user_id: str = "demo-user-1") -> dict:
    return {
        "category": "CONGESTION",
        "description": "Traffic is moving very slowly.",
        "latitude": 31.95,
        "longitude": 35.91,
        "demo_user_id": demo_user_id,
    }


@pytest.fixture
def client(tmp_path: Path):
    application = create_app(
        database_path=tmp_path / "citizen_report_api.db",
        evidence_dir=tmp_path / "evidence",
    )
    with TestClient(application) as test_client:
        yield test_client


def test_create_report_returns_201_with_backend_fields(client: TestClient) -> None:
    response = client.post("/api/citizen-reports", json=report_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "CONGESTION"
    assert body["description"] == "Traffic is moving very slowly."
    assert body["demo_user_id"] == "demo-user-1"
    assert body["report_id"]
    assert body["reported_at"] > 0
    assert body["status"] == "PENDING"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "UNKNOWN"),
        ("description", ""),
        ("latitude", 91),
        ("longitude", -181),
        ("demo_user_id", ""),
    ],
)
def test_create_report_rejects_invalid_input(
    client: TestClient,
    field: str,
    value: object,
) -> None:
    payload = report_payload()
    payload[field] = value

    response = client.post("/api/citizen-reports", json=payload)

    assert response.status_code == 422


def test_create_report_rejects_client_generated_status(client: TestClient) -> None:
    payload = report_payload()
    payload["status"] = "COMMUNITY_CONFIRMED"

    response = client.post("/api/citizen-reports", json=payload)

    assert response.status_code == 422


def test_list_reports_returns_newest_first_wrapper(client: TestClient) -> None:
    first = client.post(
        "/api/citizen-reports",
        json=report_payload("demo-user-1"),
    ).json()
    second = client.post(
        "/api/citizen-reports",
        json=report_payload("demo-user-2"),
    ).json()

    response = client.get("/api/citizen-reports")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [report["report_id"] for report in response.json()["reports"]] == [
        second["report_id"],
        first["report_id"],
    ]


def test_list_reports_returns_empty_wrapper(client: TestClient) -> None:
    response = client.get("/api/citizen-reports")

    assert response.status_code == 200
    assert response.json() == {"reports": [], "total": 0}


def test_get_report_returns_stored_report(client: TestClient) -> None:
    created = client.post("/api/citizen-reports", json=report_payload()).json()

    response = client.get(f"/api/citizen-reports/{created['report_id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_missing_report_returns_404(client: TestClient) -> None:
    response = client.get("/api/citizen-reports/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Citizen report not found: missing"


def test_openapi_lists_citizen_report_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/citizen-reports" in paths
    assert "/api/citizen-reports/{report_id}" in paths
