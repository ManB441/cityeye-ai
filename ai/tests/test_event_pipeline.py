from pathlib import Path
import json
import sys

import cv2
import numpy as np
import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from event_pipeline import EventPipeline
from events import EventStatus, EventType
from trajectory import TrajectoryManager


def make_config(**threshold_overrides: object) -> dict:
    thresholds = {
        "wrong_way_min_confidence": 0.6,
        "wrong_way_min_displacement_px": 4.0,
        "wrong_way_min_track_points": 3,
        "stopped_vehicle_seconds": 1.0,
        "stopped_vehicle_max_speed_px_per_sec": 3.0,
        "stopped_vehicle_min_track_points": 3,
        "congestion_min_vehicles": 3,
        "congestion_moderate_min_vehicles": 3,
        "congestion_min_density": 0.001,
        "congestion_max_normalized_spacing": 1.0,
        "congestion_duration_seconds": 1.0,
        "congestion_max_track_age_seconds": 0.6,
        "congestion_max_evaluation_gap_seconds": 1.0,
    }
    thresholds.update(threshold_overrides)
    return {
        "camera_name": "Test Camera",
        "latitude": 31.95,
        "longitude": 35.91,
        "trajectory_max_observation_gap_seconds": 1.0,
        "monitored_road_polygon": [[0, 0], [20, 0], [20, 20], [0, 20]],
        "allowed_direction": {"start": [10, 20], "end": [10, 0]},
        "event_thresholds": thresholds,
    }


def update_track(manager, track_id: int, points: list[tuple[float, float]]):
    state = None
    for frame, point in enumerate(points):
        state = manager.update(
            track_id=track_id,
            frame=frame,
            timestamp_sec=frame * 0.5,
            center_x=point[0],
            center_y=point[1],
        )
    assert state is not None
    return state


def test_writes_empty_events_json_when_no_rule_matches(tmp_path: Path) -> None:
    pipeline = EventPipeline(make_config(), tmp_path)

    assert pipeline.evaluate_frame(0.0, [], np.zeros((20, 20, 3), dtype=np.uint8)) == []
    events_path = pipeline.write_events_json()

    assert json.loads(events_path.read_text(encoding="utf-8")) == []
    assert not pipeline.evidence_dir.exists()


def test_real_rule_match_creates_proposed_event_and_jpg(tmp_path: Path) -> None:
    pipeline = EventPipeline(make_config(), tmp_path)
    manager = TrajectoryManager(history_size=10)
    track = update_track(manager, 7, [(10, 2), (10, 5), (10, 9)])
    frame = np.full((30, 30, 3), 120, dtype=np.uint8)

    new_events = pipeline.evaluate_frame(1.0, [track], frame)
    events_path = pipeline.write_events_json()

    assert len(new_events) == 1
    event = new_events[0]
    assert event.event_type is EventType.WRONG_WAY
    assert event.status is EventStatus.PROPOSED
    assert event.camera_name == "Test Camera"
    evidence_path = tmp_path / event.evidence_image
    assert evidence_path.is_file()
    assert cv2.imread(str(evidence_path)) is not None
    saved = json.loads(events_path.read_text(encoding="utf-8"))
    assert saved[0]["event_id"] == event.event_id
    assert saved[0]["event_type"] == "WRONG_WAY"
    assert saved[0]["status"] == "PROPOSED"
    assert saved[0]["evidence_image"].endswith(".jpg")


def test_pipeline_suppresses_duplicate_rule_event(tmp_path: Path) -> None:
    pipeline = EventPipeline(make_config(), tmp_path)
    manager = TrajectoryManager(history_size=10)
    track = update_track(manager, 7, [(10, 2), (10, 5), (10, 9)])
    frame = np.zeros((20, 20, 3), dtype=np.uint8)

    assert len(pipeline.evaluate_frame(1.0, [track], frame)) == 1
    assert pipeline.evaluate_frame(1.5, [track], frame) == []
    assert len(pipeline.events) == 1


def test_pipeline_can_generate_stopped_vehicle_event(tmp_path: Path) -> None:
    pipeline = EventPipeline(make_config(), tmp_path)
    manager = TrajectoryManager(history_size=10)
    track = update_track(manager, 4, [(10, 10), (10, 10), (10, 10)])
    frame = np.zeros((20, 20, 3), dtype=np.uint8)

    events = pipeline.evaluate_frame(1.0, [track], frame)

    assert len(events) == 1
    assert events[0].event_type is EventType.STOPPED_VEHICLE


def test_pipeline_can_generate_congestion_event(tmp_path: Path) -> None:
    pipeline = EventPipeline(make_config(), tmp_path)
    frame = np.zeros((20, 20, 3), dtype=np.uint8)

    for timestamp in (0.0, 0.5, 1.0):
        manager = TrajectoryManager(history_size=10)
        tracks = [
            manager.update(track_id, 0, timestamp, x, 10)
            for track_id, x in enumerate((5, 10, 15), start=1)
        ]
        events = pipeline.evaluate_frame(timestamp, tracks, frame)

    assert len(events) == 1
    assert events[0].event_type is EventType.CONGESTION


@pytest.mark.parametrize(
    "config_change",
    [
        {"camera_name": ""},
        {"latitude": "not-a-number"},
        {"latitude": 91},
        {"longitude": -181},
        {"allowed_direction": {}},
    ],
)
def test_rejects_invalid_event_pipeline_config(
    tmp_path: Path,
    config_change: dict,
) -> None:
    config = make_config()
    config.update(config_change)

    with pytest.raises(ValueError):
        EventPipeline(config, tmp_path)
