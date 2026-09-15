"""Camera-calibrated road-blockage reasoning built on validated track state."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from event_rules import Point, VehicleObservation, point_in_polygon
from events import EventType, Severity
from trajectory import TrackState


def polygon_area(polygon: list[Point]) -> float:
    edges = zip(polygon, polygon[1:] + polygon[:1])
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in edges)) / 2


def clip_polygon_to_box(polygon: list[Point], box: tuple[float, float, float, float]) -> list[Point]:
    """Clip a polygon to an axis-aligned detection box (Sutherland-Hodgman)."""
    x1, y1, x2, y2 = box
    output = polygon[:]
    boundaries = (
        (lambda p: p[0] >= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
        (lambda p: p[0] <= x2, lambda a, b: (x2, a[1] + (b[1] - a[1]) * (x2 - a[0]) / (b[0] - a[0]))),
        (lambda p: p[1] >= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1)),
        (lambda p: p[1] <= y2, lambda a, b: (a[0] + (b[0] - a[0]) * (y2 - a[1]) / (b[1] - a[1]), y2)),
    )
    for inside, intersect in boundaries:
        source, output = output, []
        if not source:
            break
        previous = source[-1]
        for current in source:
            current_inside, previous_inside = inside(current), inside(previous)
            if current_inside:
                if not previous_inside:
                    output.append(intersect(previous, current))
                output.append(current)
            elif previous_inside:
                output.append(intersect(previous, current))
            previous = current
    return output


@dataclass(frozen=True)
class BlockageZone:
    name: str
    polygon: list[Point]
    direction: Point
    min_vehicle_overlap: float = 0.35
    significant_overlap: float = 0.6
    upstream_min_vehicles: int = 2
    upstream_max_speed_px_per_sec: float = 8.0
    traffic_impact_seconds: float = 1.0


@dataclass(frozen=True)
class RoadBlockageMatch:
    track_id: int
    timestamp: float
    confidence: float
    severity: Severity
    explanation: str
    details: dict[str, object]
    blocking_box: tuple[int, int, int, int]
    zone_polygon: list[Point]
    event_type: EventType = EventType.ROAD_BLOCKAGE


class RoadBlockageRule:
    """Propose one blockage episode from stationary, overlap, and impact evidence."""

    def __init__(
        self,
        zones: list[BlockageZone],
        min_stationary_seconds: float,
        max_speed_px_per_sec: float,
        max_observation_gap_sec: float = 1.0,
    ) -> None:
        if not zones:
            raise ValueError("at least one blockage zone is required")
        if min_stationary_seconds <= 0 or max_speed_px_per_sec <= 0 or max_observation_gap_sec <= 0:
            raise ValueError("blockage timing and speed thresholds must be positive")
        for zone in zones:
            if not zone.name.strip() or len(zone.polygon) < 3 or polygon_area(zone.polygon) <= 0:
                raise ValueError("each blockage zone needs a name and positive-area polygon")
            if hypot(*zone.direction) == 0:
                raise ValueError("blockage zone direction must be non-zero")
            if not 0 < zone.min_vehicle_overlap <= zone.significant_overlap <= 1:
                raise ValueError("blockage overlap thresholds are invalid")
            if zone.upstream_min_vehicles < 1 or zone.upstream_max_speed_px_per_sec <= 0:
                raise ValueError("blockage upstream thresholds are invalid")
            if zone.traffic_impact_seconds <= 0:
                raise ValueError("traffic impact persistence must be positive")
        self.zones = zones
        self.min_stationary_seconds = min_stationary_seconds
        self.max_speed_px_per_sec = max_speed_px_per_sec
        self.max_observation_gap_sec = max_observation_gap_sec
        self.emitted_track_ids: set[int] = set()
        self.last_seen: dict[int, float] = {}
        self.impact_started: dict[tuple[int, str], float] = {}

    def _clear_track_impact(self, track_id: int) -> None:
        for key in [key for key in self.impact_started if key[0] == track_id]:
            self.impact_started.pop(key, None)

    def evaluate(
        self,
        timestamp: float,
        tracks: list[TrackState],
        observations: list[VehicleObservation],
    ) -> list[RoadBlockageMatch]:
        track_map = {track.track_id: track for track in tracks}
        observation_map = {
            item.track_id: item for item in observations if item.track_id is not None
        }
        for track_id in list(self.emitted_track_ids):
            track = track_map.get(track_id)
            if track is None:
                if timestamp - self.last_seen.get(track_id, timestamp) > self.max_observation_gap_sec:
                    self.emitted_track_ids.discard(track_id)
                    self._clear_track_impact(track_id)
                continue
            self.last_seen[track_id] = timestamp
            if track.pixel_speed is not None and track.pixel_speed > self.max_speed_px_per_sec:
                self.emitted_track_ids.discard(track_id)
                self._clear_track_impact(track_id)

        matches: list[RoadBlockageMatch] = []
        for track_id, track in track_map.items():
            observation = observation_map.get(track_id)
            if observation is None or track_id in self.emitted_track_ids:
                continue
            self.last_seen[track_id] = timestamp
            if track.pixel_speed is not None and track.pixel_speed > self.max_speed_px_per_sec:
                self._clear_track_impact(track_id)
                continue
            box = (observation.x1, observation.y1, observation.x2, observation.y2)
            box_area = max(0.0, observation.x2 - observation.x1) * max(0.0, observation.y2 - observation.y1)
            if box_area <= 0:
                continue
            for zone in self.zones:
                intersection_area = polygon_area(clip_polygon_to_box(zone.polygon, box))
                overlap = intersection_area / box_area
                if overlap < zone.min_vehicle_overlap:
                    continue
                direction_length = hypot(*zone.direction)
                dx, dy = zone.direction[0] / direction_length, zone.direction[1] / direction_length
                upstream = [
                    item for item in observations
                    if item.track_id != track_id
                    and point_in_polygon((item.center_x, item.center_y), zone.polygon)
                    and (item.center_x - observation.center_x) * dx
                    + (item.center_y - observation.center_y) * dy < 0
                ]
                slow_upstream = [
                    item for item in upstream
                    if item.pixel_speed is not None
                    and item.pixel_speed <= zone.upstream_max_speed_px_per_sec
                ]
                significant = overlap >= zone.significant_overlap
                impact_key = (track_id, zone.name)
                raw_impact = len(slow_upstream) >= zone.upstream_min_vehicles
                if raw_impact:
                    self.impact_started.setdefault(impact_key, timestamp)
                else:
                    self.impact_started.pop(impact_key, None)
                impact_duration = timestamp - self.impact_started.get(impact_key, timestamp)
                impact = raw_impact and impact_duration >= zone.traffic_impact_seconds
                if (
                    track.pixel_speed is None
                    or track.stationary_duration < self.min_stationary_seconds
                ):
                    continue
                confidence = 0.6 + (0.15 if significant else 0.0) + (0.15 if impact else 0.0)
                severity = Severity.HIGH if impact else Severity.MEDIUM if significant else Severity.LOW
                reasoning = "stationary vehicle overlaps active blockage zone"
                if significant:
                    reasoning += "; meaningful detection-box overlap"
                if impact:
                    reasoning += f"; {len(slow_upstream)} slow upstream vehicles"
                explanation = (
                    f"Vehicle #{track_id} remained stationary inside {zone.name} for "
                    f"{track.stationary_duration:.1f} seconds with {overlap:.0%} detection-box "
                    f"overlap."
                )
                if impact:
                    explanation += f" {len(slow_upstream)} slow vehicles were measured upstream."
                details: dict[str, object] = {
                    "track_id": track_id,
                    "vehicle_class": observation.vehicle_class,
                    "zone_name": zone.name,
                    "stationary_duration_seconds": round(track.stationary_duration, 3),
                    "vehicle_zone_overlap": round(overlap, 4),
                    "normalized_obstruction_ratio": round(intersection_area / polygon_area(zone.polygon), 4),
                    "upstream_vehicle_count": len(upstream),
                    "slow_upstream_vehicle_count": len(slow_upstream),
                    "traffic_impact_duration_seconds": round(impact_duration, 3),
                    "confidence_reasoning": reasoning,
                    "evidence_timestamp": round(timestamp, 3),
                }
                matches.append(RoadBlockageMatch(
                    track_id=track_id, timestamp=timestamp, confidence=round(confidence, 4),
                    severity=severity, explanation=explanation, details=details,
                    blocking_box=tuple(map(int, box)), zone_polygon=zone.polygon,
                ))
                self.emitted_track_ids.add(track_id)
                break
        return matches


def zones_from_config(config: list[dict]) -> list[BlockageZone]:
    zones = []
    for item in config:
        direction = item.get("direction", {})
        start, end = direction.get("start", []), direction.get("end", [])
        if len(start) != 2 or len(end) != 2:
            raise ValueError("blockage zone direction requires start and end points")
        zones.append(BlockageZone(
            name=str(item.get("name", "")).strip(),
            polygon=[tuple(point) for point in item.get("polygon", [])],
            direction=(float(end[0]) - float(start[0]), float(end[1]) - float(start[1])),
            min_vehicle_overlap=float(item.get("min_vehicle_overlap", 0.35)),
            significant_overlap=float(item.get("significant_overlap", 0.6)),
            upstream_min_vehicles=int(item.get("upstream_min_vehicles", 2)),
            upstream_max_speed_px_per_sec=float(item.get("upstream_max_speed_px_per_sec", 8.0)),
            traffic_impact_seconds=float(item.get("traffic_impact_seconds", 1.0)),
        ))
    return zones
