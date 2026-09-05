"""Validated API schemas shared by the CityEye AI Backend endpoints."""

from enum import Enum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ReportCategory(str, Enum):
    CONGESTION = "CONGESTION"
    ROAD_HAZARD = "ROAD_HAZARD"
    BLOCKED_ROAD = "BLOCKED_ROAD"
    OTHER = "OTHER"


class ReportStatus(str, Enum):
    PENDING = "PENDING"
    COMMUNITY_CONFIRMED = "COMMUNITY_CONFIRMED"


class TrafficEventBase(BaseModel):
    """Fields produced by AI and returned by the municipal API."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: EventType
    timestamp: float = Field(ge=0, allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    severity: Severity
    explanation: str = Field(min_length=1)
    camera_name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    evidence_image: str

    @field_validator("event_id", "explanation", "camera_name")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("evidence_image")
    @classmethod
    def validate_evidence_image(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value.strip()
            or path.is_absolute()
            or ".." in path.parts
            or path.suffix.lower() not in {".jpg", ".jpeg"}
        ):
            raise ValueError("evidence_image must be a safe relative JPG path")
        return value


class TrafficEventIngest(TrafficEventBase):
    """AI event accepted for storage and mandatory human review."""

    status: Literal[EventStatus.PROPOSED] = EventStatus.PROPOSED


class TrafficEventResponse(TrafficEventBase):
    """Event returned to municipal clients after storage."""

    status: EventStatus


class EventListResponse(BaseModel):
    """Stable wrapper used by polling clients."""

    model_config = ConfigDict(extra="forbid")

    events: list[TrafficEventResponse]
    total: int = Field(ge=0)


class AnalysisSummary(BaseModel):
    """Real output metadata used by the Municipal Dashboard."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["READY", "MISSING", "INVALID"]
    current_vehicle_count: int | None = Field(default=None, ge=0)
    current_people_count: int | None = Field(default=None, ge=0)
    current_bicycle_count: int | None = Field(default=None, ge=0)
    last_frame: int | None = Field(default=None, ge=0)
    total_track_records: int = Field(ge=0)
    annotated_video_available: bool
    message: str = Field(min_length=1)


class AnalysisFrame(BaseModel):
    """Vehicle counts produced by YOLO/ByteTrack for one video frame."""

    model_config = ConfigDict(extra="forbid")

    frame: int = Field(ge=0)
    timestamp_sec: float = Field(ge=0, allow_inf_nan=False)
    active_vehicle_count: int = Field(ge=0)
    cars: int = Field(ge=0)
    buses: int = Field(ge=0)
    trucks: int = Field(ge=0)
    motorcycles: int = Field(ge=0)
    people: int = Field(ge=0)
    people_in_road: int = Field(ge=0)
    tracked_people: int = Field(ge=0)
    bicycles: int = Field(ge=0)
    bicycles_in_road: int = Field(ge=0)
    tracked_bicycles: int = Field(ge=0)


class AnalysisTimeline(BaseModel):
    """Ordered real per-frame counts used to synchronize the Dashboard video."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["READY", "MISSING", "INVALID"]
    frames: list[AnalysisFrame]
    message: str = Field(min_length=1)


class ScenarioInfo(BaseModel):
    """Public metadata for one fixed real-AI demonstration scenario."""

    model_config = ConfigDict(extra="forbid")
    scenario_id: Literal["normal_traffic", "congestion", "stopped_vehicle", "rainy_traffic"]
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected_event: EventType | None
    source_url: str = Field(min_length=1)


class ScenarioListResponse(BaseModel):
    scenarios: list[ScenarioInfo]


class CitizenReportCreate(BaseModel):
    """Citizen-submitted fields accepted without user authentication."""

    model_config = ConfigDict(extra="forbid")

    category: ReportCategory
    description: str = Field(min_length=3, max_length=500)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    demo_user_id: str = Field(min_length=1, max_length=64)

    @field_validator("description", "demo_user_id", mode="before")
    @classmethod
    def strip_and_reject_blank_report_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned


class CitizenReportResponse(CitizenReportCreate):
    """Stored citizen report returned by the Backend."""

    report_id: str = Field(min_length=1)
    reported_at: float = Field(ge=0, allow_inf_nan=False)
    status: ReportStatus


class CitizenReportListResponse(BaseModel):
    """Stable report-list wrapper for the Citizen Map."""

    model_config = ConfigDict(extra="forbid")

    reports: list[CitizenReportResponse]
    total: int = Field(ge=0)
