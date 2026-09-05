from pathlib import Path
import sys

import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from event_rules import CongestionRule, TrafficState, VehicleObservation
from events import EventType, Severity
from trajectory import TrajectoryManager


ROAD_POLYGON = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]


def make_rule(**overrides: object) -> CongestionRule:
    values = {
        "monitored_polygon": ROAD_POLYGON,
        "min_vehicles": 3,
        "moderate_min_vehicles": 3,
        "min_duration_seconds": 2.0,
        "min_density": 0.001,
        "max_spacing": 1.0,
        "release_grace_seconds": 0.0,
        "max_track_age_seconds": 0.6,
        "max_evaluation_gap_seconds": 1.0,
    }
    values.update(overrides)
    return CongestionRule(**values)


def make_tracks(
    timestamp: float,
    points: list[tuple[float, float]],
):
    manager = TrajectoryManager(history_size=10)
    return [
        manager.update(
            track_id,
            frame=int(timestamp * 10),
            timestamp_sec=timestamp,
            center_x=center_x,
            center_y=center_y,
        )
        for track_id, (center_x, center_y) in enumerate(points, start=1)
    ]


def test_detects_sustained_congestion() -> None:
    rule = make_rule()

    assert rule.evaluate(0.0, make_tracks(0.0, [(5, 5), (10, 10), (15, 15)])) is None
    assert rule.evaluate(1.0, make_tracks(1.0, [(5, 5), (10, 10), (15, 15)])) is None
    match = rule.evaluate(2.0, make_tracks(2.0, [(5, 5), (10, 10), (15, 15)]))

    assert match is not None
    assert match.event_type is EventType.CONGESTION
    assert match.timestamp == 2.0
    assert match.vehicle_count == 3
    assert match.congestion_duration == 2.0
    assert match.confidence == 0.75
    assert match.severity is Severity.MEDIUM
    assert "3 vehicles" in match.explanation
    assert "ROI density" in match.explanation


def test_does_not_trigger_from_single_crowded_frame() -> None:
    rule = make_rule()

    assert rule.evaluate(0.0, make_tracks(0.0, [(5, 5), (10, 10), (15, 15)])) is None


def test_reliable_untracked_detections_contribute_to_congestion() -> None:
    rule = make_rule(min_duration_seconds=1.0)
    observations = [
        VehicleObservation(x, 10, x - 2, 7, x + 2, 13, 0.7)
        for x in (5, 10, 15)
    ]

    assert rule.evaluate(0.0, [], observations) is None
    match = rule.evaluate(1.0, [], observations)

    assert match is not None
    assert rule.last_metrics.vehicles_in_roi == 3
    assert rule.last_metrics.tracked_vehicles == 0
    assert rule.last_metrics.state is TrafficState.HEAVY_CONGESTION


def test_low_confidence_and_outside_roi_detections_are_excluded() -> None:
    rule = make_rule()
    observations = [
        VehicleObservation(5, 5, 3, 3, 7, 7, 0.8, 1),
        VehicleObservation(10, 10, 8, 8, 12, 12, 0.1),
        VehicleObservation(30, 30, 28, 28, 32, 32, 0.9, 2),
    ]

    rule.evaluate(0.0, [], observations)

    assert rule.last_metrics.detections == 3
    assert rule.last_metrics.vehicles_in_roi == 1
    assert rule.last_metrics.state is TrafficState.NORMAL


def test_counts_only_unique_tracks_inside_polygon() -> None:
    rule = make_rule(min_duration_seconds=1.0)
    inside = make_tracks(0.0, [(5, 5), (10, 10)])
    duplicate = inside[0]
    outside = make_tracks(0.0, [(30, 30)])[0]

    assert rule.evaluate(0.0, [*inside, duplicate, outside]) is None
    assert rule.congestion_started_at is None


def test_stale_tracks_are_not_counted() -> None:
    rule = make_rule()
    stale_tracks = make_tracks(0.0, [(5, 5), (10, 10), (15, 15)])

    assert rule.evaluate(1.0, stale_tracks) is None
    assert rule.congestion_started_at is None


def test_vehicle_count_drop_resets_duration() -> None:
    rule = make_rule()
    crowded = [(5, 5), (10, 10), (15, 15)]

    assert rule.evaluate(0.0, make_tracks(0.0, crowded)) is None
    assert rule.evaluate(1.0, make_tracks(1.0, crowded[:2])) is None
    assert rule.evaluate(2.0, make_tracks(2.0, crowded)) is None
    assert rule.evaluate(3.0, make_tracks(3.0, crowded)) is None
    assert rule.evaluate(4.0, make_tracks(4.0, crowded)) is not None


def test_long_evaluation_gap_resets_duration() -> None:
    rule = make_rule(max_evaluation_gap_seconds=1.0)
    crowded = [(5, 5), (10, 10), (15, 15)]

    assert rule.evaluate(0.0, make_tracks(0.0, crowded)) is None
    assert rule.evaluate(0.5, make_tracks(0.5, crowded)) is None
    assert rule.evaluate(3.0, make_tracks(3.0, crowded)) is None
    assert rule.congestion_started_at == 3.0


def test_emits_once_until_congestion_clears() -> None:
    rule = make_rule(min_duration_seconds=1.0)
    crowded = [(5, 5), (10, 10), (15, 15)]

    assert rule.evaluate(0.0, make_tracks(0.0, crowded)) is None
    assert rule.evaluate(1.0, make_tracks(1.0, crowded)) is not None
    assert rule.evaluate(2.0, make_tracks(2.0, crowded)) is None
    assert rule.evaluate(3.0, make_tracks(3.0, crowded[:2])) is None
    assert rule.evaluate(4.0, make_tracks(4.0, crowded)) is None
    assert rule.evaluate(5.0, make_tracks(5.0, crowded)) is not None


def test_large_vehicle_count_produces_high_severity() -> None:
    rule = make_rule(min_duration_seconds=1.0)
    crowded = [(2, 2), (5, 5), (8, 8), (11, 11), (14, 14)]

    assert rule.evaluate(0.0, make_tracks(0.0, crowded)) is None
    match = rule.evaluate(1.0, make_tracks(1.0, crowded))

    assert match is not None
    assert match.confidence == 0.9167
    assert match.severity is Severity.HIGH


def test_rejects_non_increasing_evaluation_timestamp() -> None:
    rule = make_rule()
    rule.evaluate(1.0, [])

    with pytest.raises(ValueError, match="timestamps must increase"):
        rule.evaluate(1.0, [])


@pytest.mark.parametrize(
    "overrides",
    [
        {"monitored_polygon": [(0, 0), (1, 1)]},
        {"min_vehicles": 1},
        {"min_duration_seconds": 0},
        {"max_track_age_seconds": 0},
        {"max_evaluation_gap_seconds": 0},
    ],
)
def test_rejects_invalid_congestion_configuration(overrides: dict) -> None:
    with pytest.raises(ValueError):
        make_rule(**overrides)
