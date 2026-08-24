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

        contiguous_observations = [latest]
        for observation in reversed(list(track.history)[:-1]):
            next_observation = contiguous_observations[0]
            if (
                next_observation.timestamp_sec - observation.timestamp_sec
                > self.max_observation_gap_sec
            ):
                break
            contiguous_observations.insert(0, observation)

        road_observations = [
            observation
            for observation in contiguous_observations
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
