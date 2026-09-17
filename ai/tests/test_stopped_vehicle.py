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
        "require_prior_motion": False,
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


def test_preexisting_parked_vehicle_does_not_trigger_when_motion_is_required() -> None:
    rule = make_rule(require_prior_motion=True)
    track = make_track([(10, 10)] * 6)

    assert track.stationary_duration >= 1.0
    assert not track.has_moved
    assert rule.evaluate(track) is None


def test_moved_then_stopped_vehicle_triggers_once_when_motion_is_required() -> None:
    manager = TrajectoryManager(
        history_size=30,
        stationary_speed_threshold=3.0,
        speed_smoothing_window=1,
        movement_state_confirmations=1,
    )
    rule = make_rule(require_prior_motion=True)
    state = None
    for frame, x in enumerate((2, 8, 10, 10, 10)):
        state = manager.update(1, frame, frame * 0.5, x, 10)

    assert state is not None and state.has_moved
    assert rule.evaluate(state) is not None
    assert rule.evaluate(state) is None


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


def test_normalized_threshold_is_resolution_independent() -> None:
    matches = []
    for scale in (100.0, 200.0):
        manager = TrajectoryManager(
            history_size=20,
            movement_scale=scale,
            stationary_normalized_speed_threshold=0.03,
            speed_smoothing_window=3,
        )
        state = None
        for frame in range(4):
            state = manager.update(1, frame, frame * 0.5, 5 + frame * scale * 0.01, 5)
        rule = make_rule(
            min_stationary_seconds=1.5,
            max_normalized_speed_per_sec=0.03,
        )
        matches.append(rule.evaluate(state))

    assert all(match is not None for match in matches)
    assert matches[0].normalized_speed == pytest.approx(matches[1].normalized_speed)


def test_stopped_episode_rearms_after_sustained_motion() -> None:
    manager = TrajectoryManager(
        history_size=30,
        movement_scale=20.0,
        stationary_normalized_speed_threshold=0.05,
        speed_smoothing_window=1,
    )
    rule = make_rule(
        min_stationary_seconds=1.0,
        max_normalized_speed_per_sec=0.05,
        release_normalized_speed_per_sec=0.1,
        rearm_moving_seconds=0.5,
    )
    state = None
    for frame, x in enumerate((10, 10, 10)):
        state = manager.update(1, frame, frame * 0.5, x, 10)
    assert rule.evaluate(state) is not None

    state = manager.update(1, 3, 1.5, 14, 10)
    assert rule.evaluate(state) is None
    state = manager.update(1, 4, 2.0, 18, 10)
    assert rule.evaluate(state) is None

    second_match = None
    for frame in (5, 6, 7):
        state = manager.update(1, frame, frame * 0.5, 18, 10)
        second_match = rule.evaluate(state) or second_match
    assert second_match is not None


def test_instantaneous_speed_guard_rejects_stale_low_median() -> None:
    manager = TrajectoryManager(
        history_size=20,
        movement_scale=100.0,
        stationary_normalized_speed_threshold=0.03,
        speed_smoothing_window=5,
    )
    for frame, x in enumerate((10, 10, 10, 10)):
        state = manager.update(1, frame, frame * 0.5, x, 10)
    state = manager.update(1, 4, 2.0, 20, 10)
    rule = make_rule(
        min_stationary_seconds=1.0,
        max_normalized_speed_per_sec=0.03,
        release_normalized_speed_per_sec=0.05,
    )

    assert state.smoothed_normalized_speed == 0.0
    assert state.normalized_speed == pytest.approx(0.2)
    assert rule.evaluate(state) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"monitored_polygon": [(0, 0), (1, 1)]},
        {"min_stationary_seconds": 0},
        {"max_speed_px_per_sec": 0},
        {"min_track_points": 1},
        {"max_observation_gap_sec": 0},
        {"max_normalized_speed_per_sec": 0},
        {"release_normalized_speed_per_sec": 0},
        {"rearm_moving_seconds": 0},
    ],
)
def test_rejects_invalid_stopped_vehicle_configuration(overrides: dict) -> None:
    with pytest.raises(ValueError):
        make_rule(**overrides)
