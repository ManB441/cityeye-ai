"""Pure traffic-event rules built on tracked vehicle trajectories."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from events import EventType, Severity
from trajectory import TrackState


Point = tuple[float, float]


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
    """Detect sustained vehicle density inside the monitored road area."""

    def __init__(
        self,
        monitored_polygon: list[Point],
        min_vehicles: int = 6,
        min_duration_seconds: float = 30.0,
        max_track_age_seconds: float = 1.0,
        max_evaluation_gap_seconds: float = 1.0,
    ) -> None:
        if len(monitored_polygon) < 3:
            raise ValueError("monitored_polygon must contain at least 3 points")
        if min_vehicles < 2:
            raise ValueError("min_vehicles must be at least 2")
        if min_duration_seconds <= 0:
            raise ValueError("min_duration_seconds must be positive")
        if max_track_age_seconds <= 0:
            raise ValueError("max_track_age_seconds must be positive")
        if max_evaluation_gap_seconds <= 0:
            raise ValueError("max_evaluation_gap_seconds must be positive")

        self.monitored_polygon = monitored_polygon
        self.min_vehicles = min_vehicles
        self.min_duration_seconds = min_duration_seconds
        self.max_track_age_seconds = max_track_age_seconds
        self.max_evaluation_gap_seconds = max_evaluation_gap_seconds
        self.congestion_started_at: float | None = None
        self.last_evaluated_at: float | None = None
        self.event_emitted = False

    def evaluate(
        self,
        timestamp: float,
        tracks: list[TrackState],
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

        active_track_ids = {
            track.track_id
            for track in tracks
            if track.history
            and 0 <= timestamp - track.history[-1].timestamp_sec
            <= self.max_track_age_seconds
            and point_in_polygon(
                (
                    track.history[-1].center_x,
                    track.history[-1].center_y,
                ),
                self.monitored_polygon,
            )
        }
        vehicle_count = len(active_track_ids)

        if vehicle_count < self.min_vehicles:
            self.congestion_started_at = None
            self.event_emitted = False
            return None

        if (
            self.congestion_started_at is None
            or evaluation_gap is not None
            and evaluation_gap > self.max_evaluation_gap_seconds
        ):
            self.congestion_started_at = timestamp
            self.event_emitted = False
            return None

        congestion_duration = timestamp - self.congestion_started_at
        if (
            congestion_duration < self.min_duration_seconds
            or self.event_emitted
        ):
            return None

        count_ratio = vehicle_count / self.min_vehicles
        confidence = round(min(1.0, 0.75 + 0.25 * (count_ratio - 1.0)), 4)
        severity = (
            Severity.HIGH
            if vehicle_count >= self.min_vehicles * 1.5
            else Severity.MEDIUM
        )
        explanation = (
            f"{vehicle_count} active vehicles remained inside the monitored "
            f"road area for {congestion_duration:.1f} seconds."
        )
        self.event_emitted = True
        return CongestionMatch(
            timestamp=timestamp,
            confidence=confidence,
            severity=severity,
            explanation=explanation,
            vehicle_count=vehicle_count,
            congestion_duration=round(congestion_duration, 3),
        )
