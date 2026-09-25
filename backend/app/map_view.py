"""Read-only geographic projection; never infer geography from image ROIs."""
import json
from pathlib import Path
import time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.live_camera import read_live_snapshot


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)


class MapCamera(BaseModel):
    model_config = ConfigDict(extra="forbid")
    camera_id: str = Field(pattern=r"^camera-[1-9][0-9]*$")
    label: str = Field(min_length=1, max_length=100)
    position: Position
    location_confirmed: bool = False
    public: bool = False
    road: list[Position] = Field(default_factory=list, max_length=100)
    traffic_calibrated: bool = False

    @model_validator(mode="after")
    def validate_road(self):
        if self.road and len({(p.lat, p.lng) for p in self.road}) < 2:
            raise ValueError("Road requires at least two distinct geographic points")
        if self.traffic_calibrated and not self.road:
            raise ValueError("Traffic mapping requires a confirmed road segment")
        return self


class MapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cameras: list[MapCamera] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_cameras(self):
        if len({camera.camera_id for camera in self.cameras}) != len(self.cameras):
            raise ValueError("Duplicate camera identity")
        return self


def load_map_config(path: str | None) -> MapConfig:
    return MapConfig.model_validate(json.loads(Path(path).read_text())) if path else MapConfig()


def map_snapshot(config, live_root, events, reports, *, citizen=False):
    features = []
    now = time.time()
    located = {c.camera_id: c for c in config.cameras if c.location_confirmed and (not citizen or c.public)}

    def feature(key, kind, label, status, geometry, **extra):
        features.append({"type": "Feature", "id": key, "geometry": geometry,
                         "properties": {"id": key, "kind": kind, "label": label, "status": status, **extra}})

    def point(camera):
        return {"type": "Point", "coordinates": [camera.position.lng, camera.position.lat]}

    for camera in located.values():
        snapshot = read_live_snapshot(live_root / camera.camera_id, camera.camera_id)
        metrics = snapshot.metrics
        # The public view exposes road conditions, not camera infrastructure.
        if not citizen:
            feature(camera.camera_id, "camera", camera.label, snapshot.reason, point(camera),
                    observed_at=metrics.timestamp if metrics else None,
                    valid_for_seconds=snapshot.valid_for_seconds,
                    vehicles=metrics.active_vehicle_count if metrics else None,
                    location_accuracy="CONFIRMED_CAMERA")
        if camera.road:
            state = metrics.traffic_state if metrics and camera.traffic_calibrated else "UNKNOWN"
            if state not in {"NORMAL", "MODERATE", "HEAVY_CONGESTION"}:
                state = "UNKNOWN"
            feature("road-" + camera.camera_id, "road", camera.label + " monitored road", state,
                    {"type": "LineString", "coordinates": [[p.lng, p.lat] for p in camera.road]},
                    observed_at=metrics.timestamp if metrics else None,
                    valid_for_seconds=snapshot.valid_for_seconds if camera.traffic_calibrated else 0,
                    location_accuracy="MONITORED_SEGMENT")
    # Each query is bounded; no display-name or event latitude/longitude fallback.
    for camera_id, camera in located.items():
        for event in events.page(limit=100, source_type="LIVE_CAMERA", source_id=camera_id).events:
            if event.status == "DISMISSED" or (citizen and event.status != "VERIFIED"):
                continue
            if not now - 86400 <= event.timestamp <= now:
                continue
            feature(event.event_id, "incident", event.event_type.value.replace("_", " "),
                    event.status.value, point(camera), observed_at=event.timestamp,
                    event_type=event.event_type.value, location_accuracy="CAMERA_AREA_APPROXIMATE",
                    description="Recorded incident within the last 24 hours; not a claim it is still active.")
    # Citizen reports are user-provided locations, not calibrated camera evidence.
    for report in reports:
        if not now - 86400 <= report.reported_at <= now:
            continue
        feature(report.report_id, "report", report.category.value.replace("_", " "), report.status.value,
                {"type": "Point", "coordinates": [report.longitude, report.latitude]},
                observed_at=report.reported_at, location_accuracy="USER_REPORTED",
                description=report.description)
    return {"type": "FeatureCollection", "features": features,
            "generated_at": now, "scope": "PUBLIC" if citizen else "OPERATIONS",
            "configured_cameras": len(located),
            "notice": "Only confirmed geographic coverage is mapped. Incident pins are approximate camera areas; reports are unverified user locations. Recent items are limited to 24 hours, 100 incidents per camera and 200 reports."}
