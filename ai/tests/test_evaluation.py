from pathlib import Path
import csv
import json
import sys

import numpy as np
import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from evaluation import (
    Detection,
    calculate_detection_quality,
    detections_in_roi,
    filter_detections,
    intersection_over_union,
    load_ground_truth,
    road_crop,
    summarize_existing_tracks,
    export_annotation_frames,
)


def test_intersection_over_union() -> None:
    assert intersection_over_union((0, 0, 10, 10), (5, 5, 15, 15)) == pytest.approx(25 / 175)
    assert intersection_over_union((0, 0, 1, 1), (2, 2, 3, 3)) == 0


def test_quality_matches_same_class_once() -> None:
    predictions = [
        Detection("car", 0.9, (0, 0, 10, 10)),
        Detection("car", 0.8, (0, 0, 10, 10)),
        Detection("motorcycle", 0.8, (20, 20, 30, 30)),
    ]
    truth = [
        Detection("car", 1.0, (0, 0, 10, 10)),
        Detection("bicycle", 1.0, (20, 20, 30, 30)),
    ]

    metrics = calculate_detection_quality(predictions, truth)

    assert metrics.true_positive == 1
    assert metrics.false_positive == 2
    assert metrics.false_negative == 1
    assert metrics.precision == pytest.approx(1 / 3)
    assert metrics.recall == pytest.approx(1 / 2)


def test_quality_without_predictions_or_truth_has_no_rates() -> None:
    metrics = calculate_detection_quality([], [])
    assert metrics.precision is None
    assert metrics.recall is None


def test_class_specific_filtering_and_roi() -> None:
    config = {
        "confidence_threshold": 0.4,
        "person_confidence_threshold": 0.2,
        "bicycle_confidence_threshold": 0.25,
        "vehicle_classes": ["car", "motorcycle"],
    }
    detections = [
        Detection("car", 0.39, (1, 1, 3, 3)),
        Detection("motorcycle", 0.5, (2, 2, 4, 4)),
        Detection("person", 0.21, (8, 8, 10, 10)),
        Detection("bicycle", 0.24, (2, 2, 4, 4)),
        Detection("bus", 0.9, (2, 2, 4, 4)),
    ]

    filtered = filter_detections(detections, config)
    inside = detections_in_roi(filtered, [(0, 0), (5, 0), (5, 5), (0, 5)])

    assert [item.class_name for item in filtered] == ["motorcycle", "person"]
    assert [item.class_name for item in inside] == ["motorcycle"]


def test_road_crop_clamps_polygon_to_frame() -> None:
    frame = np.zeros((10, 20, 3), dtype=np.uint8)
    crop, offset = road_crop(frame, [(-5, 2), (30, 2), (30, 8), (-5, 8)])
    assert crop.shape == (6, 20, 3)
    assert offset == (0, 2)


def test_load_ground_truth_requires_explicit_annotations(tmp_path: Path) -> None:
    assert load_ground_truth(None) == {}
    path = tmp_path / "truth.json"
    path.write_text(json.dumps({"frames": [{"video": "clip.mp4", "frame_index": 10, "annotations": [{"class_name": "car", "box": [1, 2, 3, 4]}]}]}))
    truth = load_ground_truth(path)
    assert truth[("clip.mp4", 10)][0].class_name == "car"


def test_summarize_existing_tracks_and_events(tmp_path: Path) -> None:
    fieldnames = ["frame", "timestamp_sec", "track_id", "class_name", "x1", "y1", "x2", "y2", "person_in_road", "bicycle_in_road"]
    with (tmp_path / "tracks.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([
            {"frame": 1, "timestamp_sec": 0.1, "track_id": 1, "class_name": "car", "x1": 1, "y1": 1, "x2": 3, "y2": 3, "person_in_road": "", "bicycle_in_road": ""},
            {"frame": 1, "timestamp_sec": 0.1, "track_id": 2, "class_name": "person", "x1": 8, "y1": 8, "x2": 10, "y2": 10, "person_in_road": "True", "bicycle_in_road": ""},
        ])
    (tmp_path / "events.json").write_text('[{"event_type":"CONGESTION"}]')
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"monitored_road_polygon": [[0, 0], [5, 0], [5, 5], [0, 5]]}))

    report = summarize_existing_tracks(tmp_path, config_path)

    assert report["frames"][0]["class_counts"]["car"] == 1
    assert report["frames"][0]["people_in_roi"] == 1
    assert report["frames"][0]["vehicles_in_roi"] == 1
    assert report["frames"][0]["tracked_objects"] == 2
    assert report["events"][0]["event_type"] == "CONGESTION"


def test_export_annotation_frames_preserves_source_metadata(tmp_path: Path) -> None:
    import cv2

    video = tmp_path / "source.mp4"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (20, 10)
    )
    for value in range(3):
        writer.write(np.full((10, 20, 3), value * 50, dtype=np.uint8))
    writer.release()

    exported = export_annotation_frames("test", video, [1], tmp_path / "frames")

    assert exported[0]["frame_index"] == 1
    assert exported[0]["timestamp_sec"] == pytest.approx(0.1)
    assert exported[0]["width"] == 20
    assert exported[0]["height"] == 10
    assert Path(exported[0]["image"]).is_file()
