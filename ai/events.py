"""Shared traffic-event contract for the CityEye AI MVP."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from pathlib import PurePosixPath
from uuid import uuid4


class EventType(str, Enum):
    WRONG_WAY = "WRONG_WAY"
    STOPPED_VEHICLE = "STOPPED_VEHICLE"
    CONGESTION = "CONGESTION"


class EventStatus(str, Enum):
    PROPOSED = "PROPOSED"
    VERIFIED = "VERIFIED"
    DISMISSED = "DISMISSED"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class TrafficEvent:
    """Validated event exchanged between the AI pipeline and Backend."""

    event_id: str
    event_type: EventType
    timestamp: float
    confidence: float
    severity: Severity
    explanation: str
    camera_name: str
    latitude: float
    longitude: float
    evidence_image: str
    status: EventStatus = EventStatus.PROPOSED

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must not be empty")
        if not isinstance(self.event_type, EventType):
            raise ValueError("event_type must be a supported EventType")
        if not isfinite(self.timestamp) or self.timestamp < 0:
            raise ValueError("timestamp must be a non-negative number of video seconds")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not isinstance(self.severity, Severity):
            raise ValueError("severity must be a supported Severity")
        if not self.explanation.strip():
            raise ValueError("explanation must not be empty")
        if not self.camera_name.strip():
            raise ValueError("camera_name must not be empty")
        if not isfinite(self.latitude) or not -90.0 <= self.latitude <= 90.0:
            raise ValueError("latitude must be between -90 and 90")
        if not isfinite(self.longitude) or not -180.0 <= self.longitude <= 180.0:
            raise ValueError("longitude must be between -180 and 180")
        if not isinstance(self.status, EventStatus):
            raise ValueError("status must be a supported EventStatus")

        evidence_path = PurePosixPath(self.evidence_image)
        if (
            not self.evidence_image.strip()
            or evidence_path.is_absolute()
            or ".." in evidence_path.parts
            or evidence_path.suffix.lower() not in {".jpg", ".jpeg"}
        ):
            raise ValueError("evidence_image must be a safe relative JPG path")

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation with stable field names."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": round(self.timestamp, 3),
            "confidence": round(self.confidence, 4),
            "severity": self.severity.value,
            "explanation": self.explanation,
            "camera_name": self.camera_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "evidence_image": self.evidence_image,
            "status": self.status.value,
        }


def create_proposed_event(
    event_type: EventType,
    timestamp: float,
    confidence: float,
    severity: Severity,
    explanation: str,
    camera_name: str,
    latitude: float,
    longitude: float,
    evidence_image: str,
) -> TrafficEvent:
    """Create an AI proposal with a unique ID and mandatory human-review status."""
    return TrafficEvent(
        event_id=str(uuid4()),
        event_type=event_type,
        timestamp=timestamp,
        confidence=confidence,
        severity=severity,
        explanation=explanation,
        camera_name=camera_name,
        latitude=latitude,
        longitude=longitude,
        evidence_image=evidence_image,
        status=EventStatus.PROPOSED,
    )
