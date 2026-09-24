"""Validated API schemas shared by the CityEye AI Backend endpoints."""

from enum import Enum

from pathlib import PurePosixPath

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventType(str, Enum):
    WRONG_WAY = "WRONG_WAY"
    STOPPED_VEHICLE = "STOPPED_VEHICLE"
    CONGESTION = "CONGESTION"
    ROAD_BLOCKAGE = "ROAD_BLOCKAGE"


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


class TrafficEventDetails(BaseModel):
    """Optional measured diagnostics emitted by supported event detectors."""

    model_config = ConfigDict(extra="forbid")

    track_id: int = Field(ge=0)
    vehicle_class: str = Field(min_length=1)
    stationary_duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    movement_value: float = Field(ge=0, allow_inf_nan=False)
    movement_unit: str = Field(min_length=1)
    instantaneous_normalized_movement: float = Field(ge=0, allow_inf_nan=False)
    pixel_speed_debug: float = Field(ge=0, allow_inf_nan=False)
    roi_status: str = Field(min_length=1)


class RoadBlockageDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track_id: int = Field(ge=0)
    vehicle_class: str = Field(min_length=1)
    zone_name: str = Field(min_length=1)
    stationary_duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    vehicle_zone_overlap: float = Field(ge=0, le=1, allow_inf_nan=False)
    normalized_obstruction_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    upstream_vehicle_count: int = Field(ge=0)
    slow_upstream_vehicle_count: int = Field(ge=0)
    traffic_impact_duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    confidence_reasoning: str = Field(min_length=1)
    evidence_timestamp: float = Field(ge=0, allow_inf_nan=False)


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
    source_type: Literal["LIVE_CAMERA", "RECORDED_SCENARIO"] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    source_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_-]+$",
        exclude_if=lambda value: value is None,
    )
    details: RoadBlockageDetails | dict[str, Any] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

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

    @model_validator(mode="after")
    def validate_event_details_match_type(self):
        if (self.source_type is None) != (self.source_id is None):
            raise ValueError("source_type and source_id must be supplied together")

        if self.event_type is EventType.ROAD_BLOCKAGE and not isinstance(
            self.details,
            RoadBlockageDetails,
        ):
            raise ValueError("ROAD_BLOCKAGE requires structured road-blockage details")

        if (
            isinstance(self.details, RoadBlockageDetails)
            and self.event_type is not EventType.ROAD_BLOCKAGE
        ):
            raise ValueError("road-blockage details require ROAD_BLOCKAGE event type")

        return self


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


class CameraHealthResponse(BaseModel):
    """Sanitized runtime state published by one selected live camera."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str = Field(min_length=1)
    source_type: Literal["RTSP"] = "RTSP"
    state: Literal["ONLINE", "STALE", "OFFLINE", "RECONNECTING"] = "OFFLINE"
    last_frame_at: float | None = Field(default=None, ge=0)
    last_connected_at: float | None = Field(default=None, ge=0)
    last_error: str | None = None
    processing_fps: float = Field(default=0.0, ge=0)
    ai_inference_fps: float = Field(default=0.0, ge=0)
    reconnect_attempts: int = Field(default=0, ge=0)
    generation: int = Field(default=0, ge=0)
    dropped_frames: int = Field(default=0, ge=0)
    heartbeat_at: float | None = Field(default=None, ge=0)
    last_visual_change_at: float | None = Field(default=None, ge=0)
    callback_sequence: int = Field(default=0, ge=0)
    visual_sequence: int = Field(default=0, ge=0)
    consecutive_similar_frames: int = Field(default=0, ge=0)
    camera_capture_fps: float = Field(default=0.0, ge=0)
    preview_publication_fps: float = Field(default=0.0, ge=0)
    preview_last_frame_at: float | None = Field(default=None, ge=0)
    buffer_pressure: int = Field(default=0, ge=0)
    checked_at: float = Field(default=0, ge=0, allow_inf_nan=False)
    valid_for_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)


class LiveMetricsResponse(BaseModel):
    """Latest real measurements for the processed live frame."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    frame: int = Field(default=0, ge=0)
    timestamp: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    generation: int = Field(default=0, ge=0)
    current_detection_count: int = Field(default=0, ge=0)
    active_vehicle_count: int = Field(default=0, ge=0)
    active_track_count: int = Field(default=0, ge=0)
    cars: int = Field(default=0, ge=0)
    buses: int = Field(default=0, ge=0)
    trucks: int = Field(default=0, ge=0)
    motorcycles: int = Field(default=0, ge=0)
    people: int = Field(default=0, ge=0)
    bicycles: int = Field(default=0, ge=0)
    traffic_state: str = "UNKNOWN"
    moving_vehicles: int = Field(default=0, ge=0)
    stationary_vehicles: int = Field(default=0, ge=0)
    unknown_movement_vehicles: int = Field(default=0, ge=0)


class LiveMetricsSnapshot(BaseModel):
    """Server-validated observation; absent/stale counts are null, never zero."""

    camera_id: str
    checked_at: float
    max_age_seconds: float
    valid_for_seconds: float
    reason: Literal[
        "FRESH",
        "MISSING",
        "INVALID",
        "STALE",
        "OFFLINE",
        "SOURCE_MISMATCH",
        "GENERATION_MISMATCH",
    ]
    health: CameraHealthResponse
    metrics: LiveMetricsResponse | None = None


class TrafficObservation(BaseModel):
    """One deduplicated historical snapshot from a live camera interval."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str = Field(min_length=1)
    interval_start: float = Field(ge=0, allow_inf_nan=False)
    observed_at: float = Field(ge=0, allow_inf_nan=False)
    generation: int = Field(ge=0)
    vehicles: int = Field(ge=0)
    cars: int = Field(ge=0)
    buses: int = Field(ge=0)
    trucks: int = Field(ge=0)
    motorcycles: int = Field(ge=0)
    bicycles: int = Field(ge=0)
    people: int = Field(ge=0)
    moving_vehicles: int = Field(ge=0)
    stationary_vehicles: int = Field(ge=0)
    traffic_status: str = Field(min_length=1)
    capture_fps: float = Field(ge=0, allow_inf_nan=False)
    ai_fps: float = Field(ge=0, allow_inf_nan=False)


class AnalyticsSeriesPoint(BaseModel):
    timestamp: float = Field(ge=0, allow_inf_nan=False)
    average_vehicles_observed: float = Field(ge=0, allow_inf_nan=False)
    peak_vehicles_observed: int = Field(ge=0)
    samples: int = Field(ge=1)
    traffic_status: str = Field(min_length=1)


class OperationalAnalyticsResponse(BaseModel):
    """Real historical analytics calculated from stored camera observations."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str = Field(min_length=1)
    requested_start: float = Field(ge=0, allow_inf_nan=False)
    requested_end: float = Field(ge=0, allow_inf_nan=False)
    data_since: float | None = Field(default=None, ge=0)
    first_sample_at: float | None = Field(default=None, ge=0)
    latest_sample_at: float | None = Field(default=None, ge=0)
    sampling_interval_seconds: int = Field(ge=1)
    bucket_seconds: int = Field(ge=1)
    samples: int = Field(ge=0)
    average_vehicles_observed: float | None = Field(default=None, ge=0)
    peak_vehicle_count: float | None = Field(default=None, ge=0)
    peak_period_start: float | None = Field(default=None, ge=0)
    peak_period_end: float | None = Field(default=None, ge=0)
    congestion_episodes: int = Field(ge=0)
    congestion_duration_minutes: float = Field(ge=0, description="Heavy sample count × interval / 60; not measured duration")
    incident_count: int = Field(ge=0)
    average_capture_fps: float | None = Field(default=None, ge=0)
    average_ai_fps: float | None = Field(default=None, ge=0)
    observed_minutes: float = Field(ge=0, description="Sample-equivalent minutes; not continuous coverage")
    vehicle_composition_observations: dict[str, int]
    incidents_by_type: dict[str, int]
    incidents_by_status: dict[str, int]
    traffic_series: list[AnalyticsSeriesPoint]
    traffic_status_samples: dict[str, int] = Field(default_factory=dict)


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

    duration_sec: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    # AI-computed traffic condition for this exact recorded frame.
    traffic_state: str = "UNKNOWN"

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

    scenario_id: Literal[
        "normal_traffic",
        "congestion",
        "stopped_vehicle",
        "rainy_traffic",
        "maydan_palestine",
    ]

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected_event: EventType | None
    source_url: str = Field(min_length=1)


class ScenarioListResponse(BaseModel):
    scenarios: list[ScenarioInfo]


class CitizenReportCreate(BaseModel):
    """Citizen report fields; authenticated API ignores the legacy demo identity."""

    model_config = ConfigDict(extra="forbid")

    category: ReportCategory
    description: str = Field(min_length=3, max_length=500)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    demo_user_id: str = Field(min_length=1, max_length=64)

    @field_validator("description", "demo_user_id", mode="before")
    @classmethod
    def strip_and_reject_blank_report_text(
        cls,
        value: object,
    ) -> object:
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