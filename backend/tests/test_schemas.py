from pathlib import Path
import sys

import pytest
from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
AI_ROOT = BACKEND_ROOT.parent / "ai"
sys.path.insert(0, str(AI_ROOT))

from app.schemas import (
    EventListResponse,
    EventStatus,
    EventType,
    Severity,
    TrafficEventIngest,
    TrafficEventResponse,
)
from events import (
    EventStatus as AiEventStatus,
    EventType as AiEventType,
    Severity as AiSeverity,
    TrafficEvent as AiTrafficEvent,
)


def valid_event_payload() -> dict:
    return {
        "event_id": "event-123",
        "event_type": "WRONG_WAY",
        "timestamp": 12.5,
        "confidence": 0.91,
        "severity": "HIGH",
        "explanation": "Track 7 moved opposite to the allowed direction.",
        "camera_name": "Demo Camera 1",
        "latitude": 31.95,
        "longitude": 35.91,
        "evidence_image": "evidence/event_0001_wrong_way.jpg",
        "status": "PROPOSED",
    }


def test_accepts_ai_event_contract_without_field_changes() -> None:
    event = TrafficEventIngest.model_validate(valid_event_payload())

    assert event.event_type is EventType.WRONG_WAY
    assert event.severity is Severity.HIGH
    assert event.status is EventStatus.PROPOSED
    assert event.model_dump(mode="json") == valid_event_payload()


def test_accepts_payload_serialized_by_real_ai_event_class() -> None:
    ai_event = AiTrafficEvent(
        event_id="ai-event-1",
        event_type=AiEventType.STOPPED_VEHICLE,
        timestamp=8.0,
        confidence=0.84,
        severity=AiSeverity.MEDIUM,
        explanation="Track 4 remained stationary for 8 seconds.",
        camera_name="Demo Camera 1",
        latitude=31.95,
        longitude=35.91,
        evidence_image="evidence/event_0002_stopped_vehicle.jpg",
        status=AiEventStatus.PROPOSED,
    )

    backend_event = TrafficEventIngest.model_validate(ai_event.to_dict())

    assert backend_event.event_id == "ai-event-1"
    assert backend_event.event_type is EventType.STOPPED_VEHICLE


@pytest.mark.parametrize("status", ["VERIFIED", "DISMISSED"])
def test_ingest_rejects_events_already_decided_by_ai(status: str) -> None:
    payload = valid_event_payload()
    payload["status"] = status

    with pytest.raises(ValidationError):
        TrafficEventIngest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_type", "COLLISION"),
        ("confidence", 1.1),
        ("timestamp", -0.1),
        ("latitude", 91),
        ("longitude", -181),
        ("explanation", "   "),
        ("camera_name", ""),
        ("evidence_image", "/private/event.jpg"),
        ("evidence_image", "../event.jpg"),
        ("evidence_image", "evidence/event.png"),
    ],
)
def test_rejects_invalid_event_fields(field: str, value: object) -> None:
    payload = valid_event_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        TrafficEventIngest.model_validate(payload)


def test_rejects_unknown_fields() -> None:
    payload = valid_event_payload()
    payload["license_plate"] = "PRIVATE"

    with pytest.raises(ValidationError):
        TrafficEventIngest.model_validate(payload)


def test_response_allows_human_review_statuses() -> None:
    payload = valid_event_payload()
    payload["status"] = "VERIFIED"

    event = TrafficEventResponse.model_validate(payload)

    assert event.status is EventStatus.VERIFIED


def test_event_list_response_has_polling_wrapper() -> None:
    event = TrafficEventResponse.model_validate(valid_event_payload())

    response = EventListResponse(events=[event], total=1)

    assert response.model_dump(mode="json")["total"] == 1
    assert response.model_dump(mode="json")["events"][0]["event_id"] == "event-123"
