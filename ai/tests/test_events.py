from pathlib import Path
import json
import sys
from uuid import UUID

import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from events import (
    EventStatus,
    EventType,
    Severity,
    TrafficEvent,
    create_proposed_event,
)


def make_event(**overrides: object) -> TrafficEvent:
    values = {
        "event_id": "event-001",
        "event_type": EventType.WRONG_WAY,
        "timestamp": 12.3456,
        "confidence": 0.87654,
        "severity": Severity.HIGH,
        "explanation": "Vehicle moved opposite to the configured direction.",
        "camera_name": "Demo Camera 1",
        "latitude": 40.7128,
        "longitude": -74.006,
        "evidence_image": "evidence/event-001.jpg",
        "status": EventStatus.PROPOSED,
    }
    values.update(overrides)
    return TrafficEvent(**values)


def test_event_contract_serializes_to_json_ready_fields() -> None:
    event = make_event()

    serialized = event.to_dict()

    assert serialized == {
        "event_id": "event-001",
        "event_type": "WRONG_WAY",
        "timestamp": 12.346,
        "confidence": 0.8765,
        "severity": "HIGH",
        "explanation": "Vehicle moved opposite to the configured direction.",
        "camera_name": "Demo Camera 1",
        "latitude": 40.7128,
        "longitude": -74.006,
        "evidence_image": "evidence/event-001.jpg",
        "status": "PROPOSED",
    }
    assert json.loads(json.dumps(serialized)) == serialized


def test_event_types_are_limited_to_fixed_mvp_scope() -> None:
    assert {event_type.value for event_type in EventType} == {
        "WRONG_WAY",
        "STOPPED_VEHICLE",
        "CONGESTION",
    }


def test_factory_creates_unique_proposed_events() -> None:
    kwargs = {
        "event_type": EventType.CONGESTION,
        "timestamp": 20.0,
        "confidence": 0.8,
        "severity": Severity.MEDIUM,
        "explanation": "Vehicle count stayed above the configured threshold.",
        "camera_name": "Demo Camera 1",
        "latitude": 40.7128,
        "longitude": -74.006,
        "evidence_image": "evidence/congestion.jpg",
    }

    first = create_proposed_event(**kwargs)
    second = create_proposed_event(**kwargs)

    assert UUID(first.event_id)
    assert first.event_id != second.event_id
    assert first.status is EventStatus.PROPOSED
    assert second.status is EventStatus.PROPOSED


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan")])
def test_rejects_invalid_confidence(confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        make_event(confidence=confidence)


@pytest.mark.parametrize("timestamp", [-0.01, float("nan")])
def test_rejects_invalid_timestamp(timestamp: float) -> None:
    with pytest.raises(ValueError, match="timestamp"):
        make_event(timestamp=timestamp)


@pytest.mark.parametrize("latitude", [-90.01, 90.01, float("nan")])
def test_rejects_invalid_latitude(latitude: float) -> None:
    with pytest.raises(ValueError, match="latitude"):
        make_event(latitude=latitude)


@pytest.mark.parametrize("longitude", [-180.01, 180.01, float("nan")])
def test_rejects_invalid_longitude(longitude: float) -> None:
    with pytest.raises(ValueError, match="longitude"):
        make_event(longitude=longitude)


@pytest.mark.parametrize(
    "evidence_image",
    ["", "/private/evidence.jpg", "../secret.jpg", "evidence/event.png"],
)
def test_rejects_unsafe_or_non_jpg_evidence_path(evidence_image: str) -> None:
    with pytest.raises(ValueError, match="safe relative JPG"):
        make_event(evidence_image=evidence_image)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("event_id", " ", "event_id"),
        ("explanation", " ", "explanation"),
        ("camera_name", " ", "camera_name"),
        ("event_type", "WRONG_WAY", "event_type"),
        ("severity", "HIGH", "severity"),
        ("status", "PROPOSED", "status"),
    ],
)
def test_rejects_invalid_required_fields(field: str, value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        make_event(**{field: value})
