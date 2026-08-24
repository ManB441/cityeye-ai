from pathlib import Path
import sys

import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from event_rules import StoppedVehicleRule
from events import EventType, Severity
from trajectory import TrajectoryManager


ROAD_POLYGON = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]


def make_rule(**overrides: object) -> StoppedVehicleRule:
    values = {
        "monitored_polygon": ROAD_POLYGON,
        "min_stationary_seconds": 1.0,
        "max_speed_px_per_sec": 3.0,
        "min_track_points": 3,
        "max_observation_gap_sec": 1.0,
    }
    values.update(overrides)
    return StoppedVehicleRule(**values)


def make_track(
    points: list[tuple[float, float]],
    timestamps: list[float] | None = None,
):
    manager = TrajectoryManager(
        history_size=30,
        stationary_speed_threshold=3.0,
        max_observation_gap_sec=1.0,
    )
    state = None
    for frame, (center_x, center_y) in enumerate(points):
        timestamp = timestamps[frame] if timestamps else frame * 0.5
        state = manager.update(
            1,
            frame=frame,
            timestamp_sec=timestamp,
            center_x=center_x,
            center_y=center_y,
        )
    assert state is not None
    return state


def test_detects_vehicle_stopped_long_enough() -> None:
    rule = make_rule()
    track = make_track([(10, 10), (10, 10), (10, 10)])

    match = rule.evaluate(track)

    assert match is not None
    assert match.event_type is EventType.STOPPED_VEHICLE
    assert match.track_id == 1
    assert match.timestamp == pytest.approx(1.0)
    assert match.pixel_speed == 0.0
    assert match.stationary_duration == 1.0
    assert match.confidence == 1.0
    assert match.severity is Severity.MEDIUM
    assert "remained nearly stationary for 1.0 seconds" in match.explanation


def test_small_tracking_jitter_still_counts_as_stationary() -> None:
    rule = make_rule()
    track = make_track([(10, 10), (11, 10), (12, 10)])

    match = rule.evaluate(track)

    assert match is not None
    assert match.pixel_speed == pytest.approx(2.0)
    assert match.confidence == pytest.approx(0.8)


def test_movement_resets_stationary_state_and_does_not_trigger() -> None:
    rule = make_rule()
    track = make_track([(10, 10), (10, 10), (18, 10)])

    assert track.stationary_duration == 0.0
    assert rule.evaluate(track) is None


def test_does_not_trigger_before_required_duration() -> None:
    rule = make_rule(min_stationary_seconds=2.0)
    track = make_track([(10, 10), (10, 10), (10, 10)])

    assert track.stationary_duration == 1.0
    assert rule.evaluate(track) is None


def test_does_not_trigger_outside_monitored_polygon() -> None:
    rule = make_rule()
    track = make_track([(30, 30), (30, 30), (30, 30)])

    assert rule.evaluate(track) is None


def test_long_detection_gap_resets_stationary_duration() -> None:
    rule = make_rule(max_observation_gap_sec=1.0)
    track = make_track(
        [(10, 10), (10, 10), (10, 10)],
        timestamps=[0.0, 0.5, 3.0],
    )

    assert track.stationary_duration == 0.0
    assert rule.evaluate(track) is None


def test_emits_only_once_for_same_track() -> None:
    rule = make_rule()
    track = make_track([(10, 10), (10, 10), (10, 10)])

    assert rule.evaluate(track) is not None
    assert rule.evaluate(track) is None


def test_long_stop_produces_high_severity() -> None:
    rule = make_rule(min_stationary_seconds=1.0)
    track = make_track([(10, 10)] * 5)

    match = rule.evaluate(track)

    assert match is not None
    assert match.stationary_duration == 2.0
    assert match.severity is Severity.HIGH


@pytest.mark.parametrize(
    "overrides",
    [
        {"monitored_polygon": [(0, 0), (1, 1)]},
        {"min_stationary_seconds": 0},
        {"max_speed_px_per_sec": 0},
        {"min_track_points": 1},
        {"max_observation_gap_sec": 0},
    ],
)
def test_rejects_invalid_stopped_vehicle_configuration(overrides: dict) -> None:
    with pytest.raises(ValueError):
        make_rule(**overrides)
