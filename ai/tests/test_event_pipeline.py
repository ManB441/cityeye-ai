from pathlib import Path
import json
import sys

import cv2
import numpy as np
import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from event_pipeline import EventPipeline
from event_rules import VehicleObservation
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
    assert saved[0]["details"]["track_id"] == 7
    assert saved[0]["details"]["direction_score"] == pytest.approx(1.0)


def test_direction_zones_work_without_global_direction(tmp_path: Path) -> None:
    config = make_config()
    config.pop("allowed_direction")
    config["direction_zones"] = [{
        "name": "northbound_lane",
        "polygon": [[0, 0], [20, 0], [20, 20], [0, 20]],
        "allowed_direction": {"start": [10, 20], "end": [10, 0]},
    }]
    pipeline = EventPipeline(config, tmp_path)
    manager = TrajectoryManager(history_size=10)
    track = update_track(manager, 7, [(10, 2), (10, 5), (10, 9)])

    events = pipeline.evaluate_frame(
        1.0, [track], np.zeros((20, 20, 3), dtype=np.uint8),
        track_classes={7: "car"},
    )

    assert events[0].details["direction_zone"] == "northbound_lane"
    assert events[0].details["vehicle_class"] == "car"


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
    manager = TrajectoryManager(
        history_size=10,
        speed_smoothing_window=1,
        movement_state_confirmations=1,
    )
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    events = []
    for frame_index, x in enumerate((2, 6, 10, 14, 14, 14, 14)):
        track = manager.update(4, frame_index, frame_index * .5, x, 10)
        events.extend(pipeline.evaluate_frame(frame_index * .5, [track], frame))

    assert len(events) == 1
    assert events[0].event_type is EventType.STOPPED_VEHICLE
    assert events[0].details["movement_state"] == "STATIONARY"
    assert events[0].details["was_previously_moving"] is True


def test_pipeline_generates_road_blockage_details_and_evidence(tmp_path: Path) -> None:
    config = make_config(road_blockage_seconds=1.0)
    config["blockage_zones"] = [{
        "name": "Main Lane",
        "polygon": [[0, 0], [20, 0], [20, 20], [0, 20]],
        "direction": {"start": [10, 20], "end": [10, 0]},
        "min_vehicle_overlap": 0.3,
        "significant_overlap": 0.6,
    }]
    pipeline = EventPipeline(config, tmp_path)
    manager = TrajectoryManager(history_size=10)
    track = update_track(manager, 4, [(10, 10), (10, 10), (10, 10)])
    detection = VehicleObservation(10, 10, 5, 5, 15, 15, 0.9, 4, 0.0, "car")
    frame = np.zeros((30, 30, 3), dtype=np.uint8)

    events = pipeline.evaluate_frame(1.0, [track], frame, [detection])
    blockage = next(event for event in events if event.event_type is EventType.ROAD_BLOCKAGE)
    saved = json.loads(pipeline.write_events_json().read_text())

    assert blockage.status is EventStatus.PROPOSED
    assert blockage.details["zone_name"] == "Main Lane"
    assert next(item for item in saved if item["event_type"] == "ROAD_BLOCKAGE")["details"]["track_id"] == 4
    evidence = cv2.imread(str(tmp_path / blockage.evidence_image))
    assert evidence is not None
    assert np.count_nonzero(evidence) > 0


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


def test_live_restart_preserves_proposals_and_evidence(tmp_path: Path) -> None:
    config = {**make_config(), "source_type": "RTSP", "camera_id": "camera-3"}
    pipeline = EventPipeline(config, tmp_path)
    manager = TrajectoryManager(history_size=10)
    track = update_track(manager, 7, [(10, 2), (10, 5), (10, 9)])
    first = pipeline.evaluate_frame(1.0, [track], np.full((30, 30, 3), 120, dtype=np.uint8))[0]
    pipeline.write_events_json()
    original_image = (tmp_path / first.evidence_image).read_bytes()
    restarted = EventPipeline(config, tmp_path)
    restarted.write_events_json()  # no new events must not erase pending delivery
    assert [event.event_id for event in restarted.events] == [first.event_id]
    other = update_track(TrajectoryManager(history_size=10), 8, [(10, 2), (10, 5), (10, 9)])
    restarted.evaluate_frame(1.0, [other], np.full((30, 30, 3), 180, dtype=np.uint8))
    restarted.write_events_json()
    payload = json.loads((tmp_path / "events.json").read_text())
    assert len(payload) == 2 and len({event["event_id"] for event in payload}) == 2
    assert (tmp_path / first.evidence_image).read_bytes() == original_image
    assert len({event["evidence_image"] for event in payload}) == 2


def test_live_invalid_delivery_file_is_never_silently_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "events.json"; path.write_text("[")
    with pytest.raises(ValueError):
        EventPipeline({**make_config(), "source_type": "RTSP"}, tmp_path)
    assert path.read_text() == "["


def test_atomic_event_publication_preserves_previous_file_on_failure(tmp_path: Path, monkeypatch) -> None:
    pipeline = EventPipeline(make_config(), tmp_path)
    pipeline.write_events_json()
    before = pipeline.events_path.read_bytes()
    def fail_replace(*args):
        raise OSError("controlled publication failure")
    monkeypatch.setattr("event_pipeline.os.replace", fail_replace)
    with pytest.raises(OSError):
        pipeline.write_events_json()
    assert pipeline.events_path.read_bytes() == before
    assert list(tmp_path.glob(".events-*.tmp")) == []
