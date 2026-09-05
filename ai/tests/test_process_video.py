from pathlib import Path
import csv
import sys


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

import pytest

from process_video import (
    build_track_row,
    format_detection_label,
    load_config,
    resolve_model_reference,
    resolve_video_path,
    mark_possible_motorcycle_riders,
    validate_video_metadata,
    write_tracks_csv,
)


def test_format_detection_label_with_track_id() -> None:
    label = format_detection_label("car", 8, 0.5087)

    assert label == "car #8 0.51"


def test_format_detection_label_without_track_id() -> None:
    label = format_detection_label("car", None, 0.4004)

    assert label == "car untracked 0.40"


def test_build_track_row_with_assigned_track() -> None:
    row = build_track_row(
        frame_idx=62,
        fps=12.5,
        track_id=1,
        class_name="car",
        confidence=0.67194,
        x1=100,
        y1=200,
        x2=300,
        y2=400,
        pixel_speed=2.5,
        stationary_duration=2.0,
    )

    assert row == {
        "frame": 62,
        "timestamp_sec": 4.96,
        "track_id": 1,
        "class_name": "car",
        "confidence": 0.6719,
        "x1": 100,
        "y1": 200,
        "x2": 300,
        "y2": 400,
        "center_x": 200.0,
        "center_y": 300.0,
        "pixel_speed": 2.5,
        "stationary_duration": 2.0,
        "person_in_road": None,
        "possible_rider": None,
    }


def test_build_track_row_with_unassigned_track_and_half_pixel_center() -> None:
    row = build_track_row(
        frame_idx=1,
        fps=10.0,
        track_id=None,
        class_name="truck",
        confidence=0.55555,
        x1=100,
        y1=201,
        x2=301,
        y2=400,
    )

    assert row["timestamp_sec"] == 0.1
    assert row["track_id"] is None
    assert row["confidence"] == 0.5555
    assert row["center_x"] == 200.5
    assert row["center_y"] == 300.5
    assert row["pixel_speed"] is None
    assert row["stationary_duration"] is None


def test_validate_video_metadata_keeps_valid_fps() -> None:
    assert validate_video_metadata(fps=12.5, width=768, height=432) == 12.5


@pytest.mark.parametrize("fps", [0.0, -1.0, float("nan")])
def test_validate_video_metadata_uses_fallback_for_invalid_fps(fps: float) -> None:
    assert validate_video_metadata(fps=fps, width=768, height=432) == 25.0


@pytest.mark.parametrize(
    ("width", "height"),
    [(0, 432), (768, 0), (-1, 432), (768, -1)],
)
def test_validate_video_metadata_rejects_invalid_dimensions(
    width: int,
    height: int,
) -> None:
    with pytest.raises(RuntimeError, match="Invalid video dimensions"):
        validate_video_metadata(fps=12.5, width=width, height=height)


def test_load_config_reads_valid_json(tmp_path: Path) -> None:
    config_path = tmp_path / "camera.json"
    config_path.write_text(
        '{"video_source": "sample.mp4", "confidence_threshold": 0.4}',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["video_source"] == "sample.mp4"
    assert config["confidence_threshold"] == 0.4


def test_load_config_rejects_missing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError, match="Config not found"):
        load_config(config_path)


def test_load_config_reports_invalid_json_location(tmp_path: Path) -> None:
    config_path = tmp_path / "camera.json"
    config_path.write_text(
        '{\n  "confidence_threshold": 0.4\n  "model": "yolov8n.pt"\n}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"Invalid JSON.*line 3, column 3"):
        load_config(config_path)


def test_resolve_video_path_relative_to_ai_root(tmp_path: Path) -> None:
    video_path = tmp_path / "sample_videos" / "traffic.mp4"
    video_path.parent.mkdir()
    video_path.touch()

    resolved = resolve_video_path(
        config={"video_source": "sample_videos/traffic.mp4"},
        ai_root=tmp_path,
        cli_video=None,
    )

    assert resolved == video_path


def test_resolve_video_path_accepts_absolute_cli_path(tmp_path: Path) -> None:
    video_path = tmp_path / "traffic.mp4"
    video_path.touch()

    resolved = resolve_video_path(
        config={},
        ai_root=tmp_path / "unused",
        cli_video=str(video_path),
    )

    assert resolved == video_path


def test_resolve_video_path_rejects_missing_video(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Video not found"):
        resolve_video_path(
            config={"video_source": "missing.mp4"},
            ai_root=tmp_path,
            cli_video=None,
        )


def test_resolve_model_reference_prefers_weights_in_ai_root(tmp_path: Path) -> None:
    model_path = tmp_path / "yolov8n.pt"
    model_path.touch()

    resolved = resolve_model_reference("yolov8n.pt", ai_root=tmp_path)

    assert resolved == str(model_path)


def test_resolve_model_reference_preserves_absolute_path(tmp_path: Path) -> None:
    model_path = tmp_path / "custom.pt"

    resolved = resolve_model_reference(str(model_path), ai_root=tmp_path / "unused")

    assert resolved == str(model_path)


def test_resolve_model_reference_keeps_downloadable_model_name(tmp_path: Path) -> None:
    resolved = resolve_model_reference("yolo11n.pt", ai_root=tmp_path)

    assert resolved == "yolo11n.pt"


def test_write_tracks_csv_writes_header_for_no_detections(tmp_path: Path) -> None:
    tracks_path = tmp_path / "tracks.csv"

    write_tracks_csv(tracks_path, track_rows=[])

    with tracks_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
        fieldnames = reader.fieldnames

    assert fieldnames == [
        "frame",
        "timestamp_sec",
        "track_id",
        "class_name",
        "confidence",
        "x1",
        "y1",
        "x2",
        "y2",
        "center_x",
        "center_y",
        "pixel_speed",
        "stationary_duration",
        "person_in_road",
        "possible_rider",
    ]
    assert rows == []


def test_write_tracks_csv_preserves_unassigned_track_as_blank(tmp_path: Path) -> None:
    tracks_path = tmp_path / "tracks.csv"
    row = build_track_row(
        frame_idx=1,
        fps=10.0,
        track_id=None,
        class_name="car",
        confidence=0.5,
        x1=10,
        y1=20,
        x2=30,
        y2=40,
    )

    write_tracks_csv(tracks_path, track_rows=[row])

    with tracks_path.open(newline="", encoding="utf-8") as csv_file:
        saved_rows = list(csv.DictReader(csv_file))

    assert len(saved_rows) == 1
    assert saved_rows[0]["track_id"] == ""
    assert saved_rows[0]["class_name"] == "car"
    assert saved_rows[0]["pixel_speed"] == ""
    assert saved_rows[0]["stationary_duration"] == ""


def test_marks_person_overlapping_motorcycle_as_possible_rider() -> None:
    rows = [
        {"class_name": "person", "x1": 10, "y1": 10, "x2": 20, "y2": 30, "possible_rider": False},
        {"class_name": "motorcycle", "x1": 8, "y1": 20, "x2": 24, "y2": 36, "possible_rider": None},
    ]

    mark_possible_motorcycle_riders(rows)

    assert rows[0]["possible_rider"] is True


def test_does_not_mark_unrelated_person_as_motorcycle_rider() -> None:
    rows = [
        {"class_name": "person", "x1": 100, "y1": 100, "x2": 120, "y2": 150, "possible_rider": False},
        {"class_name": "motorcycle", "x1": 10, "y1": 20, "x2": 30, "y2": 40, "possible_rider": None},
    ]

    mark_possible_motorcycle_riders(rows)

    assert rows[0]["possible_rider"] is False
