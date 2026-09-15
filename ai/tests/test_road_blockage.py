from pathlib import Path
import sys

import pytest

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from event_rules import VehicleObservation
from events import EventType, Severity
from road_blockage import BlockageZone, RoadBlockageRule
from trajectory import TrajectoryManager


ZONE = BlockageZone(
    name="Main Lane",
    polygon=[(0, 0), (100, 0), (100, 100), (0, 100)],
    direction=(0, -1),
    min_vehicle_overlap=0.35,
    significant_overlap=0.6,
    upstream_min_vehicles=2,
    upstream_max_speed_px_per_sec=8.0,
)


def make_rule(**overrides):
    values = dict(zones=[ZONE], min_stationary_seconds=1.0, max_speed_px_per_sec=3.0, max_observation_gap_sec=1.0)
    values.update(overrides)
    return RoadBlockageRule(**values)


def observation(track_id, x, y, speed=0.0, size=20, vehicle_class="car"):
    return VehicleObservation(x, y, x-size/2, y-size/2, x+size/2, y+size/2, 0.9, track_id, speed, vehicle_class)


def update(manager, track_id, points, start_frame=0):
    state = None
    for offset, (x, y) in enumerate(points):
        frame = start_frame + offset
        state = manager.update(track_id, frame, frame * 0.5, x, y)
    return state


def stopped_track(track_id=1, point=(50, 50)):
    manager = TrajectoryManager(history_size=20, stationary_speed_threshold=3.0, max_observation_gap_sec=1.0)
    return manager, update(manager, track_id, [point, point, point])


def test_vehicle_moving_through_zone_is_not_blockage():
    manager = TrajectoryManager(history_size=20)
    track = update(manager, 1, [(20, 50), (40, 50), (60, 50)])
    assert make_rule().evaluate(1.0, [track], [observation(1, 60, 50, 40)]) == []


def test_brief_stop_is_not_blockage():
    manager = TrajectoryManager(history_size=20)
    track = update(manager, 1, [(50, 50), (50, 50)])
    assert make_rule().evaluate(0.5, [track], [observation(1, 50, 50)]) == []


@pytest.mark.parametrize("point", [(120, 50), (50, 120)])
def test_stationary_vehicle_outside_active_zone_or_at_curb_is_not_blockage(point):
    _, track = stopped_track(point=point)
    assert make_rule().evaluate(1.0, [track], [observation(1, *point)]) == []


def test_stationary_vehicle_inside_zone_produces_measured_candidate():
    _, track = stopped_track()
    match = make_rule().evaluate(1.0, [track], [observation(1, 50, 50)])[0]
    assert match.event_type is EventType.ROAD_BLOCKAGE
    assert match.details["zone_name"] == "Main Lane"
    assert match.details["vehicle_zone_overlap"] == 1.0
    assert match.severity is Severity.MEDIUM
    assert "1.0 seconds" in match.explanation


def test_persistent_obstruction_emits_only_one_event():
    _, track = stopped_track()
    rule = make_rule()
    obs = [observation(1, 50, 50)]
    assert len(rule.evaluate(1.0, [track], obs)) == 1
    assert rule.evaluate(1.5, [track], obs) == []
    assert rule.evaluate(2.0, [track], obs) == []


def test_vehicle_moving_again_rearms_episode():
    manager, track = stopped_track()
    rule = make_rule()
    assert rule.evaluate(1.0, [track], [observation(1, 50, 50)])
    track = update(manager, 1, [(70, 50)], start_frame=3)
    assert rule.evaluate(1.5, [track], [observation(1, 70, 50, 40)]) == []
    track = update(manager, 1, [(70, 50), (70, 50), (70, 50)], start_frame=4)
    assert rule.evaluate(3.0, [track], [observation(1, 70, 50)])


def test_detection_gap_rearms_without_creating_false_event():
    _, track = stopped_track()
    rule = make_rule()
    assert rule.evaluate(1.0, [track], [observation(1, 50, 50)])
    assert rule.evaluate(1.5, [], []) == []
    assert rule.evaluate(2.1, [], []) == []
    assert 1 not in rule.emitted_track_ids


def test_traffic_accumulation_strengthens_evidence():
    manager = TrajectoryManager(history_size=20, stationary_speed_threshold=3.0)
    rule = make_rule()
    match = None
    for frame in range(3):
        track = update(manager, 1, [(50, 40)], start_frame=frame)
        observations = [observation(1, 50, 40), observation(2, 45, 60, speed=2), observation(3, 55, 80, speed=3)]
        matches = rule.evaluate(frame * 0.5, [track], observations)
        match = matches[0] if matches else match
    assert match is not None
    assert match.severity is Severity.HIGH
    assert match.confidence == 0.9
    assert match.details["slow_upstream_vehicle_count"] == 2
    assert match.details["traffic_impact_duration_seconds"] == 1.0
    assert "2 slow vehicles" in match.explanation


def test_movement_resets_accumulated_traffic_impact():
    manager = TrajectoryManager(history_size=20, stationary_speed_threshold=3.0)
    rule = make_rule()
    upstream = [observation(2, 45, 60, speed=2), observation(3, 55, 80, speed=3)]
    track = update(manager, 1, [(50, 40), (50, 40)])
    assert rule.evaluate(0.5, [track], [observation(1, 50, 40), *upstream]) == []

    track = update(manager, 1, [(70, 40)], start_frame=2)
    assert rule.evaluate(1.0, [track], [observation(1, 70, 40, speed=40), *upstream]) == []

    track = update(manager, 1, [(70, 40), (70, 40), (70, 40)], start_frame=3)
    match = rule.evaluate(2.5, [track], [observation(1, 70, 40), *upstream])[0]
    assert match.severity is Severity.MEDIUM
    assert match.details["traffic_impact_duration_seconds"] == 0.0


def test_partial_box_overlap_below_threshold_is_rejected():
    _, track = stopped_track(point=(105, 50))
    assert make_rule().evaluate(1.0, [track], [observation(1, 105, 50, size=20)]) == []
