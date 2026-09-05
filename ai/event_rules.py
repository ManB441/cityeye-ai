"""Pure traffic-event rules built on tracked vehicle trajectories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import hypot

from events import EventType, Severity
from trajectory import TrackState


Point = tuple[float, float]


class TrafficState(str, Enum):
    NORMAL = "NORMAL"
    MODERATE = "MODERATE"
    HEAVY_CONGESTION = "HEAVY_CONGESTION"


@dataclass(frozen=True)
class VehicleObservation:
    center_x: float
    center_y: float
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    track_id: int | None = None
    pixel_speed: float | None = None


@dataclass(frozen=True)
class TrafficMetrics:
    detections: int
    vehicles_in_roi: int
    tracked_vehicles: int
    traffic_density: float
    average_spacing: float | None
    average_movement: float | None
    congestion_candidate: bool
    congestion_duration: float
    state: TrafficState


@dataclass(frozen=True)
class WrongWayMatch:
    """Event-ready result produced when one track moves against traffic."""

    track_id: int
    timestamp: float
    confidence: float
    severity: Severity
    explanation: str
    event_type: EventType = EventType.WRONG_WAY


@dataclass(frozen=True)
class StoppedVehicleMatch:
    """Event-ready result produced when one vehicle remains stationary."""

    track_id: int
    timestamp: float
    confidence: float
    severity: Severity
    explanation: str
    stationary_duration: float
    pixel_speed: float
    event_type: EventType = EventType.STOPPED_VEHICLE


@dataclass(frozen=True)
class CongestionMatch:
    """Event-ready result produced by sustained vehicle density."""

    timestamp: float
    confidence: float
    severity: Severity
    explanation: str
    vehicle_count: int
    congestion_duration: float
    traffic_density: float = 0.0
    traffic_state: TrafficState = TrafficState.HEAVY_CONGESTION
    event_type: EventType = EventType.CONGESTION


def point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    """Return True for points inside or on the boundary of a polygon."""
    if len(polygon) < 3:
        raise ValueError("monitored_road_polygon must contain at least 3 points")

    px, py = point
    inside = False
    previous_x, previous_y = polygon[-1]

    for current_x, current_y in polygon:
        cross = (px - previous_x) * (current_y - previous_y) - (
            py - previous_y
        ) * (current_x - previous_x)
        on_segment = (
            abs(cross) <= 1e-9
            and min(previous_x, current_x) <= px <= max(previous_x, current_x)
            and min(previous_y, current_y) <= py <= max(previous_y, current_y)
        )
        if on_segment:
            return True

        crosses_ray = (current_y > py) != (previous_y > py)
        if crosses_ray:
            intersection_x = previous_x + (py - previous_y) * (
                current_x - previous_x
            ) / (current_y - previous_y)
            if px < intersection_x:
                inside = not inside

        previous_x, previous_y = current_x, current_y

    return inside


def contiguous_observations(
    track: TrackState,
    max_observation_gap_sec: float,
) -> list:
    """Return only the latest time-contiguous section of one track history."""
    if max_observation_gap_sec <= 0:
        raise ValueError("max_observation_gap_sec must be positive")
    if not track.history:
        return []

    observations = [track.history[-1]]
    for observation in reversed(list(track.history)[:-1]):
        next_observation = observations[0]
        if (
            next_observation.timestamp_sec - observation.timestamp_sec
            > max_observation_gap_sec
        ):
            break
        observations.insert(0, observation)
    return observations


class WrongWayRule:
    """Detect sustained movement opposite to one configured road direction."""

    def __init__(
        self,
        monitored_polygon: list[Point],
        allowed_start: Point,
        allowed_end: Point,
        min_confidence: float = 0.6,
        min_displacement_px: float = 20.0,
        min_track_points: int = 3,
        max_observation_gap_sec: float = 1.0,
    ) -> None:
        if len(monitored_polygon) < 3:
            raise ValueError("monitored_polygon must contain at least 3 points")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if min_displacement_px <= 0:
            raise ValueError("min_displacement_px must be positive")
        if min_track_points < 2:
            raise ValueError("min_track_points must be at least 2")
        if max_observation_gap_sec <= 0:
            raise ValueError("max_observation_gap_sec must be positive")

        allowed_dx = allowed_end[0] - allowed_start[0]
        allowed_dy = allowed_end[1] - allowed_start[1]
        allowed_length = hypot(allowed_dx, allowed_dy)
        if allowed_length == 0:
            raise ValueError("allowed_direction start and end must be different")

        self.monitored_polygon = monitored_polygon
        self.allowed_vector = (allowed_dx, allowed_dy)
        self.allowed_length = allowed_length
        self.min_confidence = min_confidence
        self.min_displacement_px = min_displacement_px
        self.min_track_points = min_track_points
        self.max_observation_gap_sec = max_observation_gap_sec
        self.emitted_track_ids: set[int] = set()

    def evaluate(self, track: TrackState) -> WrongWayMatch | None:
        """Return one match per track when its reliable movement is opposite."""
        if track.track_id in self.emitted_track_ids or not track.history:
            return None

        latest = track.history[-1]
        if not point_in_polygon(
            (latest.center_x, latest.center_y),
            self.monitored_polygon,
        ):
            return None

        road_observations = [
            observation
            for observation in contiguous_observations(
                track,
                self.max_observation_gap_sec,
            )
            if point_in_polygon(
                (observation.center_x, observation.center_y),
                self.monitored_polygon,
            )
        ]
        if len(road_observations) < self.min_track_points:
            return None

        first = road_observations[0]
        movement_dx = latest.center_x - first.center_x
        movement_dy = latest.center_y - first.center_y
        movement_length = hypot(movement_dx, movement_dy)
        if movement_length < self.min_displacement_px:
            return None

        allowed_dx, allowed_dy = self.allowed_vector
        cosine = (
            movement_dx * allowed_dx + movement_dy * allowed_dy
        ) / (movement_length * self.allowed_length)
        cosine = max(-1.0, min(1.0, cosine))
        opposition_confidence = max(0.0, -cosine)
        if opposition_confidence < self.min_confidence:
            return None

        confidence = round(opposition_confidence, 4)
        severity = Severity.HIGH if confidence >= 0.85 else Severity.MEDIUM
        explanation = (
            f"Track {track.track_id} moved {movement_length:.1f} pixels opposite "
            f"to the configured allowed direction "
            f"(direction confidence {confidence:.2f})."
        )
        self.emitted_track_ids.add(track.track_id)
        return WrongWayMatch(
            track_id=track.track_id,
            timestamp=latest.timestamp_sec,
            confidence=confidence,
            severity=severity,
            explanation=explanation,
        )


class StoppedVehicleRule:
    """Detect one tracked vehicle stopped inside the monitored road area."""

    def __init__(
        self,
        monitored_polygon: list[Point],
        min_stationary_seconds: float = 8.0,
        max_speed_px_per_sec: float = 3.0,
        min_track_points: int = 3,
        max_observation_gap_sec: float = 1.0,
    ) -> None:
        if len(monitored_polygon) < 3:
            raise ValueError("monitored_polygon must contain at least 3 points")
        if min_stationary_seconds <= 0:
            raise ValueError("min_stationary_seconds must be positive")
        if max_speed_px_per_sec <= 0:
            raise ValueError("max_speed_px_per_sec must be positive")
        if min_track_points < 2:
            raise ValueError("min_track_points must be at least 2")
        if max_observation_gap_sec <= 0:
            raise ValueError("max_observation_gap_sec must be positive")

        self.monitored_polygon = monitored_polygon
        self.min_stationary_seconds = min_stationary_seconds
        self.max_speed_px_per_sec = max_speed_px_per_sec
        self.min_track_points = min_track_points
        self.max_observation_gap_sec = max_observation_gap_sec
        self.emitted_track_ids: set[int] = set()

    def evaluate(self, track: TrackState) -> StoppedVehicleMatch | None:
        """Return one match when a reliable track remains stopped long enough."""
        if track.track_id in self.emitted_track_ids or not track.history:
            return None
        if track.pixel_speed is None:
            return None

        latest = track.history[-1]
        if not point_in_polygon(
            (latest.center_x, latest.center_y),
            self.monitored_polygon,
        ):
            return None

        recent_observations = contiguous_observations(
            track,
            self.max_observation_gap_sec,
        )
        if len(recent_observations) < self.min_track_points:
            return None
        if track.pixel_speed > self.max_speed_px_per_sec:
            return None
        if track.stationary_duration < self.min_stationary_seconds:
            return None

        speed_score = max(
            0.0,
            1.0 - track.pixel_speed / self.max_speed_px_per_sec,
        )
        duration_score = min(
            1.0,
            track.stationary_duration / self.min_stationary_seconds,
        )
        confidence = round(0.7 * duration_score + 0.3 * speed_score, 4)
        severity = (
            Severity.HIGH
            if track.stationary_duration >= self.min_stationary_seconds * 2
            else Severity.MEDIUM
        )
        explanation = (
            f"Track {track.track_id} remained nearly stationary for "
            f"{track.stationary_duration:.1f} seconds at "
            f"{track.pixel_speed:.1f} pixels/second."
        )

        self.emitted_track_ids.add(track.track_id)
        return StoppedVehicleMatch(
            track_id=track.track_id,
            timestamp=latest.timestamp_sec,
            confidence=confidence,
            severity=severity,
            explanation=explanation,
            stationary_duration=round(track.stationary_duration, 3),
            pixel_speed=round(track.pixel_speed, 3),
        )


class CongestionRule:
    """Classify traffic using count, occupancy, spacing, movement, and time."""

    def __init__(
        self,
        monitored_polygon: list[Point],
        min_vehicles: int = 16,
        moderate_min_vehicles: int | None = None,
        min_density: float = 0.04,
        max_spacing: float = 0.12,
        max_movement: float = 0.12,
        min_detection_confidence: float = 0.30,
        perspective_weight_strength: float = 0.5,
        min_duration_seconds: float = 5.0,
        release_grace_seconds: float = 0.75,
        max_track_age_seconds: float = 1.0,
        max_evaluation_gap_seconds: float = 1.0,
    ) -> None:
        if len(monitored_polygon) < 3:
            raise ValueError("monitored_polygon must contain at least 3 points")
        if min_vehicles < 2:
            raise ValueError("min_vehicles must be at least 2")
        moderate_min_vehicles = moderate_min_vehicles or max(
            2, int(min_vehicles * 0.75)
        )
        if not 2 <= moderate_min_vehicles <= min_vehicles:
            raise ValueError("moderate_min_vehicles must be between 2 and min_vehicles")
        if min_density <= 0 or max_spacing <= 0 or max_movement <= 0:
            raise ValueError("density, spacing, and movement thresholds must be positive")
        if not 0 <= min_detection_confidence <= 1:
            raise ValueError("min_detection_confidence must be between 0 and 1")
        if release_grace_seconds < 0:
            raise ValueError("release_grace_seconds must not be negative")
        if not 0 <= perspective_weight_strength <= 2:
            raise ValueError("perspective_weight_strength must be between 0 and 2")
        if min_duration_seconds <= 0:
            raise ValueError("min_duration_seconds must be positive")
        if max_track_age_seconds <= 0:
            raise ValueError("max_track_age_seconds must be positive")
        if max_evaluation_gap_seconds <= 0:
            raise ValueError("max_evaluation_gap_seconds must be positive")

        self.monitored_polygon = monitored_polygon
        self.min_vehicles = min_vehicles
        self.moderate_min_vehicles = moderate_min_vehicles
        self.min_density = min_density
        self.max_spacing = max_spacing
        self.max_movement = max_movement
        self.min_detection_confidence = min_detection_confidence
        self.perspective_weight_strength = perspective_weight_strength
        self.min_duration_seconds = min_duration_seconds
        self.release_grace_seconds = release_grace_seconds
        self.max_track_age_seconds = max_track_age_seconds
        self.max_evaluation_gap_seconds = max_evaluation_gap_seconds
        self.congestion_started_at: float | None = None
        self.last_evaluated_at: float | None = None
        self.event_emitted = False
        self.last_candidate_at: float | None = None
        self.last_metrics = TrafficMetrics(
            0, 0, 0, 0.0, None, None, False, 0.0, TrafficState.NORMAL
        )
        edges = zip(monitored_polygon, monitored_polygon[1:] + monitored_polygon[:1])
        self.roi_area = abs(
            sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in edges)
        ) / 2
        if self.roi_area <= 0:
            raise ValueError("monitored_polygon must have a positive area")
        ys = [point[1] for point in monitored_polygon]
        self.roi_min_y, self.roi_max_y = min(ys), max(ys)

    def calculate_metrics(
        self, timestamp: float, observations: list[VehicleObservation]
    ) -> TrafficMetrics:
        accepted = [
            observation
            for observation in observations
            if observation.confidence >= self.min_detection_confidence
            and point_in_polygon(
                (observation.center_x, observation.center_y), self.monitored_polygon
            )
        ]
        scale = self.roi_area ** 0.5
        weighted_area = 0.0
        for item in accepted:
            vertical = (item.center_y - self.roi_min_y) / max(
                1.0, self.roi_max_y - self.roi_min_y
            )
            weight = 1.0 + self.perspective_weight_strength * (
                1.0 - max(0.0, min(1.0, vertical))
            )
            weighted_area += (
                max(0.0, item.x2 - item.x1)
                * max(0.0, item.y2 - item.y1)
                * weight
            )
        density = min(1.0, weighted_area / self.roi_area)
        nearest = []
        for index, item in enumerate(accepted):
            distances = [
                hypot(item.center_x - other.center_x, item.center_y - other.center_y)
                / scale
                for other_index, other in enumerate(accepted)
                if other_index != index
            ]
            if distances:
                nearest.append(min(distances))
        speeds = [item.pixel_speed/scale for item in accepted if item.pixel_speed is not None]
        spacing = sum(nearest)/len(nearest) if nearest else None
        movement = sum(speeds)/len(speeds) if speeds else None
        count = len(accepted)
        dense = density >= self.min_density
        close = spacing is not None and spacing <= self.max_spacing
        movement_ok = movement is None or movement <= self.max_movement
        candidate = (
            count >= self.min_vehicles and (dense or close)
        ) or (
            count >= self.moderate_min_vehicles
            and dense
            and close
            and movement_ok
        )
        if candidate:
            self.last_candidate_at = timestamp
        grace = (
            self.last_candidate_at is not None
            and timestamp - self.last_candidate_at <= self.release_grace_seconds
        )
        sustained = candidate or (self.congestion_started_at is not None and grace)
        if not sustained:
            self.congestion_started_at = None
            self.event_emitted = False
        elif self.congestion_started_at is None:
            self.congestion_started_at = timestamp
        duration = (
            0.0
            if self.congestion_started_at is None
            else timestamp - self.congestion_started_at
        )
        if duration >= self.min_duration_seconds:
            state = TrafficState.HEAVY_CONGESTION
        elif sustained or count >= self.moderate_min_vehicles:
            state = TrafficState.MODERATE
        else:
            state = TrafficState.NORMAL
        return TrafficMetrics(
            detections=len(observations),
            vehicles_in_roi=count,
            tracked_vehicles=len(
                {item.track_id for item in accepted if item.track_id is not None}
            ),
            traffic_density=round(density, 4),
            average_spacing=None if spacing is None else round(spacing, 4),
            average_movement=None if movement is None else round(movement, 4),
            congestion_candidate=candidate,
            congestion_duration=round(duration, 3),
            state=state,
        )

    def evaluate(
        self,
        timestamp: float,
        tracks: list[TrackState],
        observations: list[VehicleObservation] | None = None,
    ) -> CongestionMatch | None:
        """Return one match after enough active vehicles persist long enough."""
        if timestamp < 0:
            raise ValueError("timestamp must be non-negative")
        if self.last_evaluated_at is not None and timestamp <= self.last_evaluated_at:
            raise ValueError("evaluation timestamps must increase")

        evaluation_gap = (
            None
            if self.last_evaluated_at is None
            else timestamp - self.last_evaluated_at
        )
        self.last_evaluated_at = timestamp

        if evaluation_gap is not None and evaluation_gap > self.max_evaluation_gap_seconds:
            self.congestion_started_at = self.last_candidate_at = None
            self.event_emitted = False
        if observations is None:
            unique_tracks = {track.track_id: track for track in tracks}
            observations = [
                VehicleObservation(
                    center_x=track.history[-1].center_x,
                    center_y=track.history[-1].center_y,
                    x1=track.history[-1].center_x - 1,
                    y1=track.history[-1].center_y - 1,
                    x2=track.history[-1].center_x + 1,
                    y2=track.history[-1].center_y + 1,
                    confidence=1.0,
                    track_id=track.track_id,
                    pixel_speed=track.pixel_speed,
                )
                for track in unique_tracks.values()
                if track.history
                and 0
                <= timestamp - track.history[-1].timestamp_sec
                <= self.max_track_age_seconds
            ]
        self.last_metrics = self.calculate_metrics(timestamp, observations)
        if self.last_metrics.state is not TrafficState.HEAVY_CONGESTION or self.event_emitted:
            return None
        vehicle_count = self.last_metrics.vehicles_in_roi
        congestion_duration = self.last_metrics.congestion_duration
        count_ratio = vehicle_count / self.min_vehicles
        confidence = round(min(1.0, 0.75 + 0.25 * (count_ratio - 1.0)), 4)
        severity = (
            Severity.HIGH
            if vehicle_count >= self.min_vehicles * 1.5
            else Severity.MEDIUM
        )
        explanation = (
            f"Heavy congestion confirmed with {vehicle_count} vehicles, ROI density "
            f"{self.last_metrics.traffic_density:.3f}, and {congestion_duration:.1f} "
            "seconds of sustained crowding."
        )
        self.event_emitted = True
        return CongestionMatch(
            timestamp=timestamp,
            confidence=confidence,
            severity=severity,
            explanation=explanation,
            vehicle_count=vehicle_count,
            congestion_duration=round(congestion_duration, 3),
            traffic_density=self.last_metrics.traffic_density,
            traffic_state=self.last_metrics.state,
        )
