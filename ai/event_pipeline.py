"""Connect trajectory rules to JSON events and JPG evidence files."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from road_blockage import RoadBlockageMatch, RoadBlockageRule, zones_from_config

from event_rules import (
    CongestionRule,
    CongestionMatch,
    StoppedVehicleMatch,
    StoppedVehicleRule,
    VehicleObservation,
    WrongWayMatch,
    WrongWayRule,
)
from calibration import resolve_camera_calibration
from events import EventStatus, EventType, Severity, TrafficEvent, create_proposed_event
from trajectory import TrackState


class EventPipeline:
    """Evaluate configured rules and persist event-ready demo artifacts."""

    def __init__(self, config: dict, output_dir: Path, frame_size: tuple[int, int] | None = None) -> None:
        self.calibration = resolve_camera_calibration(config, frame_size)
        if self.calibration is not None:
            config = self.calibration.config
        enabled = lambda rule: self.calibration is None or self.calibration.enabled(rule)
        polygon = [tuple(point) for point in config.get("monitored_road_polygon", [])]
        allowed_direction = config.get("allowed_direction", {})
        allowed_start = tuple(allowed_direction.get("start", []))
        allowed_end = tuple(allowed_direction.get("end", []))

        self.camera_name = str(config.get("camera_name", "")).strip()
        if not self.camera_name:
            raise ValueError("camera_name must not be empty")
        self.camera_id = str(config.get("camera_id", self.camera_name)).strip()
        self.source_type = str(config.get("source_type", "VIDEO_FILE")).upper()
        try:
            self.latitude = float(config["latitude"])
            self.longitude = float(config["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("latitude and longitude must be configured numbers") from exc
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError("latitude must be between -90 and 90")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError("longitude must be between -180 and 180")

        thresholds = config.get("event_thresholds", {})
        observation_gap = float(
            config.get("trajectory_max_observation_gap_seconds", 1.0)
        )
        direction_zones = config.get("direction_zones")
        if direction_zones is not None and not isinstance(direction_zones, list):
            raise ValueError("direction_zones must be a list")
        if enabled("wrong_way") and not direction_zones and (len(allowed_start) != 2 or len(allowed_end) != 2):
            raise ValueError("allowed_direction must contain two-point start and end")
        zone_configs = direction_zones if direction_zones else [{
            "name": None,
            "polygon": polygon,
            "allowed_direction": {"start": allowed_start, "end": allowed_end},
        }]
        if not enabled("wrong_way"):
            zone_configs = []
        self.wrong_way_rules = []
        for zone in zone_configs:
            if not isinstance(zone, dict):
                raise ValueError("each direction zone must be an object")
            zone_direction = zone.get("allowed_direction", {})
            zone_start = tuple(zone_direction.get("start", []))
            zone_end = tuple(zone_direction.get("end", []))
            zone_polygon = [tuple(point) for point in zone.get("polygon", polygon)]
            if len(zone_start) != 2 or len(zone_end) != 2:
                raise ValueError(
                    "each direction zone must contain a two-point allowed_direction"
                )
            self.wrong_way_rules.append(WrongWayRule(
                monitored_polygon=zone_polygon,
                allowed_start=zone_start,
                allowed_end=zone_end,
                min_confidence=float(thresholds.get("wrong_way_min_confidence", 0.6)),
                min_displacement_px=float(thresholds.get("wrong_way_min_displacement_px", 20.0)),
                min_track_points=int(thresholds.get("wrong_way_min_track_points", 3)),
                max_observation_gap_sec=observation_gap,
                min_normalized_displacement=(
                    float(thresholds["wrong_way_min_normalized_displacement"])
                    if "wrong_way_min_normalized_displacement" in thresholds else None
                ),
                min_opposite_observations=int(
                    thresholds.get("wrong_way_min_opposite_observations", 1)
                ),
                zone_name=zone.get("name"),
            ))
        self.wrong_way_rule = self.wrong_way_rules[0] if self.wrong_way_rules else None
        stopped_polygon = [
            tuple(point)
            for point in config.get("stopped_vehicle_polygon", polygon)
        ]
        self.stopped_vehicle_rule = None if not enabled("stopped_vehicle") else StoppedVehicleRule(
            monitored_polygon=stopped_polygon,
            min_stationary_seconds=float(
                thresholds.get("stopped_vehicle_seconds", 8.0)
            ),
            max_speed_px_per_sec=float(
                thresholds.get("stopped_vehicle_max_speed_px_per_sec", 3.0)
            ),
            min_track_points=int(
                thresholds.get("stopped_vehicle_min_track_points", 3)
            ),
            max_observation_gap_sec=observation_gap,
            max_normalized_speed_per_sec=(
                float(thresholds["stopped_vehicle_max_normalized_speed_per_sec"])
                if "stopped_vehicle_max_normalized_speed_per_sec" in thresholds
                else None
            ),
            release_normalized_speed_per_sec=(
                float(thresholds["stopped_vehicle_release_normalized_speed_per_sec"])
                if "stopped_vehicle_release_normalized_speed_per_sec" in thresholds
                else None
            ),
            rearm_moving_seconds=float(
                thresholds.get("stopped_vehicle_rearm_moving_seconds", 1.0)
            ),
            require_prior_motion=bool(
                thresholds.get("stopped_vehicle_require_prior_motion", True)
            ),
        )
        self.congestion_rule = None if not enabled("congestion") else CongestionRule(
            monitored_polygon=polygon,
            min_vehicles=int(thresholds.get("congestion_min_vehicles", 16)),
            moderate_min_vehicles=int(
                thresholds.get(
                    "congestion_moderate_min_vehicles",
                    min(12, int(thresholds.get("congestion_min_vehicles", 16))),
                )
            ),
            min_density=float(thresholds.get("congestion_min_density", 0.04)),
            max_spacing=float(
                thresholds.get("congestion_max_normalized_spacing", 0.12)
            ),
            max_movement=float(
                thresholds.get("congestion_max_normalized_movement", 0.12)
            ),
            min_detection_confidence=float(
                thresholds.get("congestion_min_detection_confidence", 0.30)
            ),
            perspective_weight_strength=float(
                thresholds.get("congestion_perspective_weight_strength", 0.5)
            ),
            min_duration_seconds=float(
                thresholds.get("congestion_duration_seconds", 5.0)
            ),
            max_track_age_seconds=float(
                thresholds.get("congestion_max_track_age_seconds", 1.0)
            ),
            max_evaluation_gap_seconds=float(
                thresholds.get("congestion_max_evaluation_gap_seconds", 1.0)
            ),
            release_grace_seconds=float(
                thresholds.get("congestion_release_grace_seconds", 0.75)
            ),
        )
        blockage_zones = zones_from_config(config.get("blockage_zones", []))
        self.road_blockage_rule = (
            None
            if not blockage_zones
            else RoadBlockageRule(
                zones=blockage_zones,
                min_stationary_seconds=float(
                    thresholds.get(
                        "road_blockage_seconds",
                        thresholds.get("stopped_vehicle_seconds", 8.0),
                    )
                ),
                max_speed_px_per_sec=float(
                    thresholds.get("stopped_vehicle_max_speed_px_per_sec", 3.0)
                ),
                max_observation_gap_sec=observation_gap,
            )
        )
        self.output_dir = output_dir
        self.evidence_dir = output_dir / "evidence"
        self.events_path = output_dir / "events.json"
        self.events: list[TrafficEvent] = []
        if self.source_type == "RTSP" and self.events_path.exists():
            # Replay outstanding proposals across producer restarts. Never silently
            # replace an unreadable delivery file with an empty history.
            payloads = json.loads(self.events_path.read_text(encoding="utf-8"))
            if not isinstance(payloads, list):
                raise ValueError("Live event delivery file must contain a list")
            seen: set[str] = set()
            for payload in payloads:
                event = TrafficEvent(**{
                    **payload,
                    "event_type": EventType(payload["event_type"]),
                    "status": EventStatus(payload.get("status", "PROPOSED")),
                    "severity": Severity(payload["severity"]),
                })
                if event.event_id not in seen:
                    self.events.append(event)
                    seen.add(event.event_id)

    def evaluate_frame(
        self,
        timestamp: float,
        tracks: list[TrackState],
        annotated_frame: np.ndarray,
        detections: list[VehicleObservation] | None = None,
        track_classes: dict[int, str] | None = None,
    ) -> list[TrafficEvent]:
        """Evaluate all rules once and save evidence for new real matches."""
        new_matches = []
        unique_tracks = {track.track_id: track for track in tracks}
        for track in unique_tracks.values():
            for wrong_way_rule in self.wrong_way_rules:
                wrong_way = wrong_way_rule.evaluate(track)
                if wrong_way is not None:
                    new_matches.append(wrong_way)
                    break
            stopped = self.stopped_vehicle_rule.evaluate(track) if self.stopped_vehicle_rule is not None else None
            if stopped is not None:
                new_matches.append(stopped)

        congestion = None if self.congestion_rule is None else self.congestion_rule.evaluate(
            timestamp,
            list(unique_tracks.values()),
            observations=detections,
        )
        if congestion is not None:
            new_matches.append(congestion)
        if self.road_blockage_rule is not None:
            new_matches.extend(
                self.road_blockage_rule.evaluate(
                    timestamp,
                    list(unique_tracks.values()),
                    detections or [],
                )
            )

        new_events = []
        track_classes = track_classes or {}
        for match in new_matches:
            evidence_name = (
                f"event_{int(match.timestamp * 1000)}_{uuid4().hex[:8]}_"
                f"{match.event_type.value.lower()}.jpg"
                if self.source_type == "RTSP"
                else f"event_{len(self.events) + 1:04d}_{match.event_type.value.lower()}.jpg"
            )
            evidence_relative_path = f"evidence/{evidence_name}"
            details = self._event_details(
                match,
                track_classes,
                unique_tracks,
            )
            details.update({
                "source_type": self.source_type,
                "camera_id": self.camera_id,
                "timestamp_kind": (
                    "WALL_CLOCK_UNIX" if self.source_type == "RTSP" else "VIDEO_SECONDS"
                ),
            })
            event = create_proposed_event(
                event_type=match.event_type,
                timestamp=match.timestamp,
                confidence=match.confidence,
                severity=match.severity,
                explanation=match.explanation,
                camera_name=self.camera_name,
                latitude=self.latitude,
                longitude=self.longitude,
                evidence_image=evidence_relative_path,
                details=details,
            )
            evidence_frame = self._render_blockage_evidence(annotated_frame, match)
            self._save_evidence(evidence_frame, evidence_name)
            self.events.append(event)
            new_events.append(event)
        return new_events

    @staticmethod
    def _event_details(
        match: object,
        track_classes: dict[int, str],
        tracks: dict[int, TrackState] | None = None,
    ) -> dict:
        tracks = tracks or {}
        if isinstance(match, RoadBlockageMatch):
            return dict(match.details)
        if isinstance(match, StoppedVehicleMatch):
            track = tracks.get(match.track_id)
            return {
                "track_id": match.track_id,
                "vehicle_class": track_classes.get(match.track_id),
                "stationary_duration_seconds": match.stationary_duration,
                "movement_value": match.normalized_speed,
                "movement_unit": "roi_diagonals_per_second",
                "instantaneous_normalized_movement": (
                    match.instantaneous_normalized_speed
                ),
                "pixel_speed_debug": match.pixel_speed,
                "roi_status": "INSIDE",
                "movement_state": (
                    track.movement_state.value if track is not None else None
                ),
                "was_previously_moving": (
                    track.has_moved if track is not None else None
                ),
            }
        if isinstance(match, WrongWayMatch):
            track = tracks.get(match.track_id)
            return {
                "track_id": match.track_id,
                "vehicle_class": track_classes.get(match.track_id),
                "trajectory_displacement_px": match.displacement_px,
                "normalized_displacement": match.normalized_displacement,
                "direction_score": match.direction_score,
                "measured_direction": list(match.measured_direction),
                "allowed_direction": list(match.allowed_direction),
                "direction_zone": match.direction_zone,
                "roi_status": "INSIDE",
                "movement_state": (
                    track.movement_state.value if track is not None else None
                ),
            }
        if isinstance(match, CongestionMatch):
            return {
                "vehicle_count": match.vehicle_count,
                "congestion_duration_seconds": match.congestion_duration,
                "traffic_density": match.traffic_density,
                "traffic_state": match.traffic_state.value,
            }
        return {}

    def _render_blockage_evidence(
        self, frame: np.ndarray, match: object
    ) -> np.ndarray:
        if not isinstance(match, RoadBlockageMatch):
            return frame
        rendered = frame.copy()
        polygon = np.array(match.zone_polygon, dtype=np.int32)
        cv2.polylines(rendered, [polygon], True, (0, 165, 255), 2)
        x1, y1, x2, y2 = match.blocking_box
        cv2.rectangle(rendered, (x1, y1), (x2, y2), (0, 0, 255), 3)
        cv2.putText(
            rendered,
            f"ROAD BLOCKAGE | TRACK {match.track_id} | {match.timestamp:.1f}s",
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        return rendered

    def _save_evidence(self, frame: np.ndarray, filename: str) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = self.evidence_dir / filename
        if not cv2.imwrite(str(evidence_path), frame):
            raise RuntimeError(f"Could not save evidence image: {evidence_path}")

    def write_events_json(self) -> Path:
        """Write a valid list even when no event thresholds were met."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.output_dir,
                                             prefix=".events-", suffix=".tmp", delete=False) as events_file:
                temporary = Path(events_file.name)
                json.dump([event.to_dict() for event in self.events], events_file,
                          indent=2, ensure_ascii=False)
                events_file.write("\n")
                events_file.flush()
                os.fsync(events_file.fileno())
            os.replace(temporary, self.events_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return self.events_path
