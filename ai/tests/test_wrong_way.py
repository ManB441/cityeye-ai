from pathlib import Path
import sys

import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from event_rules import WrongWayRule, point_in_polygon
from events import EventType, Severity
from trajectory import TrajectoryManager


ROAD_POLYGON = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def make_rule(**overrides: object) -> WrongWayRule:
    values = {
        "monitored_polygon": ROAD_POLYGON,
        "allowed_start": (5.0, 10.0),
        "allowed_end": (5.0, 0.0),
        "min_confidence": 0.6,
        "min_displacement_px": 4.0,
        "min_track_points": 3,
    }
    values.update(overrides)
    return WrongWayRule(**values)


def make_track(track_id: int, points: list[tuple[float, float]]):
    manager = TrajectoryManager(history_size=20)
    state = None
    for frame, (center_x, center_y) in enumerate(points):
        state = manager.update(
            track_id,
            frame=frame,
            timestamp_sec=frame * 0.1,
            center_x=center_x,
            center_y=center_y,
        )
    assert state is not None
    return state


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        ((5.0, 5.0), True),
        ((0.0, 5.0), True),
        ((10.0, 10.0), True),
        ((11.0, 5.0), False),
    ],
)
def test_point_in_polygon_includes_boundary(
    point: tuple[float, float],
    expected: bool,
) -> None:
    assert point_in_polygon(point, ROAD_POLYGON) is expected


def test_detects_track_moving_opposite_to_allowed_direction() -> None:
    rule = make_rule()
    track = make_track(7, [(5, 2), (5, 4), (5, 7)])

    match = rule.evaluate(track)

    assert match is not None
    assert match.event_type is EventType.WRONG_WAY
    assert match.track_id == 7
    assert match.timestamp == pytest.approx(0.2)
    assert match.confidence == 1.0
    assert match.severity is Severity.HIGH
    assert "Track 7 moved 5.0 pixels opposite" in match.explanation


def test_does_not_trigger_for_allowed_direction() -> None:
    rule = make_rule()
    track = make_track(1, [(5, 8), (5, 5), (5, 2)])

    assert rule.evaluate(track) is None


def test_does_not_trigger_outside_monitored_polygon() -> None:
    rule = make_rule()
    track = make_track(1, [(20, 2), (20, 5), (20, 8)])

    assert rule.evaluate(track) is None


def test_does_not_trigger_with_insufficient_history() -> None:
    rule = make_rule(min_track_points=4)
    track = make_track(1, [(5, 2), (5, 5), (5, 8)])

    assert rule.evaluate(track) is None


def test_does_not_trigger_for_small_jitter() -> None:
    rule = make_rule(min_displacement_px=4.0)
    track = make_track(1, [(5, 5), (5.2, 5.4), (4.9, 5.8)])

    assert rule.evaluate(track) is None


def test_does_not_connect_movement_across_long_detection_gap() -> None:
    rule = make_rule(max_observation_gap_sec=0.5)
    manager = TrajectoryManager(history_size=20, max_observation_gap_sec=0.5)
    manager.update(1, frame=0, timestamp_sec=0.0, center_x=5, center_y=2)
    manager.update(1, frame=1, timestamp_sec=0.1, center_x=5, center_y=3)
    manager.update(1, frame=20, timestamp_sec=2.0, center_x=5, center_y=8)
    track = manager.update(1, frame=21, timestamp_sec=2.1, center_x=5, center_y=9)

    assert rule.evaluate(track) is None


def test_does_not_trigger_when_opposition_confidence_is_below_threshold() -> None:
    rule = make_rule(min_confidence=0.9)
    track = make_track(1, [(2, 2), (4, 4), (7, 7)])

    assert rule.evaluate(track) is None


def test_angled_opposite_movement_produces_medium_severity() -> None:
    rule = make_rule(min_confidence=0.6)
    track = make_track(4, [(2, 2), (4, 4), (7, 7)])

    match = rule.evaluate(track)

    assert match is not None
    assert match.confidence == pytest.approx(0.7071)
    assert match.severity is Severity.MEDIUM


def test_emits_only_once_for_same_track() -> None:
    rule = make_rule()
    track = make_track(3, [(5, 2), (5, 4), (5, 7)])

    first = rule.evaluate(track)
    second = rule.evaluate(track)

    assert first is not None
    assert second is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"monitored_polygon": [(0, 0), (1, 1)]},
        {"allowed_start": (1, 1), "allowed_end": (1, 1)},
        {"min_confidence": 1.1},
        {"min_displacement_px": 0},
        {"min_track_points": 1},
        {"max_observation_gap_sec": 0},
    ],
)
def test_rejects_invalid_wrong_way_configuration(overrides: dict) -> None:
    with pytest.raises(ValueError):
        make_rule(**overrides)
