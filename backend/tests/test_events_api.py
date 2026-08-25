from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app


def event_payload(event_id: str = "event-1", timestamp: float = 10.0) -> dict:
    return {
        "event_id": event_id,
        "event_type": "WRONG_WAY",
        "timestamp": timestamp,
        "confidence": 0.91,
        "severity": "HIGH",
        "explanation": "Track moved opposite to the allowed direction.",
        "camera_name": "Demo Camera 1",
        "latitude": 31.95,
        "longitude": 35.91,
        "evidence_image": f"evidence/{event_id}.jpg",
        "status": "PROPOSED",
    }


@pytest.fixture
def client(tmp_path: Path):
    application = create_app(tmp_path / "api_test.db")
    with TestClient(application) as test_client:
        yield test_client


def test_ingest_event_returns_201_and_proposed_event(client: TestClient) -> None:
    response = client.post("/api/events/ingest", json=event_payload())

    assert response.status_code == 201
    assert response.json() == event_payload()


def test_ingest_duplicate_event_returns_409(client: TestClient) -> None:
    assert client.post("/api/events/ingest", json=event_payload()).status_code == 201

    response = client.post("/api/events/ingest", json=event_payload())

    assert response.status_code == 409
    assert response.json()["detail"] == "Event already exists: event-1"


def test_ingest_invalid_event_returns_422(client: TestClient) -> None:
    payload = event_payload()
    payload["confidence"] = 1.5

    response = client.post("/api/events/ingest", json=payload)

    assert response.status_code == 422


def test_list_events_returns_polling_wrapper_newest_first(client: TestClient) -> None:
    client.post("/api/events/ingest", json=event_payload("older", 5.0))
    client.post("/api/events/ingest", json=event_payload("newer", 12.0))

    response = client.get("/api/events")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [event["event_id"] for event in response.json()["events"]] == [
        "newer",
        "older",
    ]


def test_list_events_returns_empty_wrapper(client: TestClient) -> None:
    response = client.get("/api/events")

    assert response.status_code == 200
    assert response.json() == {"events": [], "total": 0}


def test_get_event_returns_stored_event(client: TestClient) -> None:
    client.post("/api/events/ingest", json=event_payload())

    response = client.get("/api/events/event-1")

    assert response.status_code == 200
    assert response.json()["event_id"] == "event-1"


def test_get_missing_event_returns_404(client: TestClient) -> None:
    response = client.get("/api/events/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found: missing"


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [("verify", "VERIFIED"), ("dismiss", "DISMISSED")],
)
def test_review_action_updates_event_status(
    client: TestClient,
    action: str,
    expected_status: str,
) -> None:
    client.post("/api/events/ingest", json=event_payload())

    response = client.post(f"/api/events/event-1/{action}")

    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    assert client.get("/api/events/event-1").json()["status"] == expected_status


@pytest.mark.parametrize("action", ["verify", "dismiss"])
def test_review_missing_event_returns_404(client: TestClient, action: str) -> None:
    response = client.post(f"/api/events/missing/{action}")

    assert response.status_code == 404


def test_openapi_lists_all_event_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/events/ingest" in paths
    assert "/api/events" in paths
    assert "/api/events/{event_id}" in paths
    assert "/api/events/{event_id}/verify" in paths
    assert "/api/events/{event_id}/dismiss" in paths
