#!/usr/bin/env python3
"""
CityEye AI — video detection and tracking (MVP slice 1).

Reads a local MP4, runs pretrained YOLO vehicle detection with ByteTrack,
draws bounding boxes with class labels and track IDs, evaluates traffic-event
rules, and writes:
  - output/annotated.mp4
  - output/tracks.csv
  - output/events.json
  - output/evidence/*.jpg when a real event rule matches
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from event_pipeline import EventPipeline
from event_rules import VehicleObservation, point_in_polygon
from trajectory import TrajectoryManager

# COCO class IDs for vehicles we care about
COCO_VEHICLE_IDS = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}
COCO_PERSON_ID = 0
COCO_BICYCLE_ID = 1
COCO_ROAD_USER_IDS = {
    COCO_PERSON_ID: "person",
    COCO_BICYCLE_ID: "bicycle",
    **COCO_VEHICLE_IDS,
}

CLASS_COLORS = {
    "person": (255, 220, 0),
    "bicycle": (255, 180, 60),
    "car": (0, 200, 0),
    "motorcycle": (255, 140, 0),
    "bus": (200, 0, 200),
    "truck": (0, 140, 255),
}

TRACK_FIELDNAMES = [
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
    "bicycle_in_road",
    "possible_rider",
]


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}\n"
            f"Copy ai/config/camera.json.example to ai/config/camera.json and edit paths."
        )
    try:
        with config_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in config {config_path} at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc


def resolve_video_path(config: dict, ai_root: Path, cli_video: str | None) -> Path:
    if cli_video:
        video_path = Path(cli_video)
        if not video_path.is_absolute():
            video_path = ai_root / video_path
    else:
        source = config.get("video_source", "sample_videos/traffic.mp4")
        video_path = Path(source)
        if not video_path.is_absolute():
            video_path = ai_root / video_path
    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}\n"
            "Place an MP4 at that path or pass --video /path/to/file.mp4"
        )
    return video_path


def resolve_model_reference(model_name: str, ai_root: Path) -> str:
    """Prefer local AI weights while preserving Ultralytics model-name downloads."""
    model_path = Path(model_name)
    if model_path.is_absolute():
        return str(model_path)

    ai_model_path = ai_root / model_path
    if ai_model_path.exists():
        return str(ai_model_path)

    return model_name


def draw_detection(
    frame: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    class_name: str,
    track_id: int | None,
    confidence: float,
) -> None:
    color = CLASS_COLORS.get(class_name, (255, 255, 255))
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    label = format_detection_label(class_name, track_id, confidence)
    (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(frame, (x1, y1 - th - baseline - 4), (x1 + tw, y1), color, -1)
    cv2.putText(
        frame,
        label,
        (x1, y1 - baseline - 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )


def format_detection_label(
    class_name: str,
    track_id: int | None,
    confidence: float,
) -> str:
    """Build a label without presenting an unassigned detection as a real track."""
    track_label = f"#{track_id}" if track_id is not None else "untracked"
    return f"{class_name} {track_label} {confidence:.2f}"


def build_track_row(
    frame_idx: int,
    fps: float,
    track_id: int | None,
    class_name: str,
    confidence: float,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    pixel_speed: float | None = None,
    stationary_duration: float | None = None,
    person_in_road: bool | None = None,
    bicycle_in_road: bool | None = None,
    possible_rider: bool | None = None,
) -> dict:
    """Convert one vehicle observation into the stable tracks.csv schema."""
    return {
        "frame": frame_idx,
        "timestamp_sec": round(frame_idx / fps, 3),
        "track_id": track_id,
        "class_name": class_name,
        "confidence": round(confidence, 4),
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "center_x": round((x1 + x2) / 2, 1),
        "center_y": round((y1 + y2) / 2, 1),
        "pixel_speed": round(pixel_speed, 3) if pixel_speed is not None else None,
        "stationary_duration": (
            round(stationary_duration, 3) if stationary_duration is not None else None
        ),
        "person_in_road": person_in_road,
        "bicycle_in_road": bicycle_in_road,
        "possible_rider": possible_rider,
    }


def intersection_over_smaller_box(first: dict, second: dict) -> float:
    """Measure strong spatial association without requiring identical box sizes."""
    intersection_width = max(0, min(first["x2"], second["x2"]) - max(first["x1"], second["x1"]))
    intersection_height = max(0, min(first["y2"], second["y2"]) - max(first["y1"], second["y1"]))
    intersection = intersection_width * intersection_height
    first_area = max(1, (first["x2"] - first["x1"]) * (first["y2"] - first["y1"]))
    second_area = max(1, (second["x2"] - second["x1"]) * (second["y2"] - second["y1"]))
    return intersection / min(first_area, second_area)


def mark_possible_riders(rows: list[dict], overlap_threshold: float = 0.35) -> None:
    """Flag people strongly overlapping motorcycles or bicycles."""
    rideables = [
        row for row in rows
        if row["class_name"] in {"motorcycle", "bicycle"}
    ]
    for row in rows:
        if row["class_name"] == "person":
            row["possible_rider"] = any(
                intersection_over_smaller_box(row, rideable) >= overlap_threshold
                for rideable in rideables
            )


mark_possible_motorcycle_riders = mark_possible_riders


def validate_video_metadata(fps: float, width: int, height: int) -> float:
    """Validate frame dimensions and return a usable FPS value."""
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid video dimensions: {width}x{height}")
    if not np.isfinite(fps) or fps <= 0:
        return 25.0
    return float(fps)


def write_tracks_csv(tracks_path: Path, track_rows: list[dict]) -> None:
    """Write the stable tracks.csv header and any vehicle observations."""
    with tracks_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer_csv = csv.DictWriter(csv_file, fieldnames=TRACK_FIELDNAMES)
        writer_csv.writeheader()
        writer_csv.writerows(track_rows)


def process_video(
    video_path: Path,
    config: dict,
    output_dir: Path,
    model_name: str | None = None,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    annotated_path = output_dir / "annotated.mp4"
    tracks_path = output_dir / "tracks.csv"

    confidence_threshold = float(config.get("confidence_threshold", 0.25))
    inference_image_size = int(config.get("inference_image_size", 960))
    iou_threshold = float(config.get("iou_threshold", 0.7))
    debug_traffic = bool(config.get("debug_traffic_analysis", False))
    tracker_reference = Path(
        config.get("tracker", "config/bytetrack_cityeye.yaml")
    )
    if not tracker_reference.is_absolute():
        tracker_reference = Path(__file__).resolve().parent / tracker_reference
    allowed_vehicle_classes = set(
        config.get("vehicle_classes", list(COCO_VEHICLE_IDS.values()))
    )
    person_detection_enabled = bool(config.get("person_detection_enabled", True))
    person_confidence_threshold = float(
        config.get("person_confidence_threshold", 0.22)
    )
    bicycle_confidence_threshold = float(
        config.get("bicycle_confidence_threshold", 0.22)
    )
    model_reference = model_name or config.get("model", "yolov8n.pt")
    model_path = resolve_model_reference(
        model_reference,
        Path(__file__).resolve().parent,
    )
    event_thresholds = config.get("event_thresholds", {})
    stationary_speed_threshold = float(
        event_thresholds.get(
            "stopped_vehicle_max_speed_px_per_sec",
            event_thresholds.get("stopped_vehicle_max_speed_px", 3.0),
        )
    )
    trajectory_manager = TrajectoryManager(
        history_size=int(config.get("trajectory_history_size", 30)),
        stationary_speed_threshold=stationary_speed_threshold,
        max_observation_gap_sec=float(
            config.get("trajectory_max_observation_gap_seconds", 1.0)
        ),
    )
    event_pipeline = EventPipeline(config=config, output_dir=output_dir)

    print(f"Loading model: {model_path}")
    model = YOLO(model_path)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    raw_fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    try:
        fps = validate_video_metadata(raw_fps, width, height)
    except RuntimeError:
        cap.release()
        raise

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(annotated_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        writer.release()
        raise RuntimeError(f"Could not create output video: {annotated_path}")

    track_rows: list[dict] = []
    frame_idx = 0

    print(
        f"Processing {video_path.name} "
        f"({width}x{height} @ {fps:.1f} fps, ~{total_frames} frames)"
    )

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            results = model.track(
                frame,
                persist=True,
                tracker=str(tracker_reference),
                conf=min(
                    confidence_threshold,
                    person_confidence_threshold,
                    bicycle_confidence_threshold,
                ),
                imgsz=inference_image_size,
                iou=iou_threshold,
                classes=list(COCO_ROAD_USER_IDS.keys()),
                verbose=False,
            )

            vehicle_count = 0
            current_track_states = {}
            vehicle_observations: list[VehicleObservation] = []
            frame_rows: list[dict] = []
            raw_people = people_after_confidence = people_in_roi = tracked_people = 0
            raw_bicycles = bicycles_after_confidence = bicycles_in_roi = 0
            tracked_bicycles = 0
            raw_motorcycles = motorcycles_after_confidence = tracked_motorcycles = 0
            if results and results[0].boxes is not None and len(results[0].boxes) > 0:
                boxes = results[0].boxes
                for box in boxes:
                    cls_id = int(box.cls.item())
                    class_name = COCO_ROAD_USER_IDS.get(cls_id)
                    if class_name == "person":
                        raw_people += 1
                    elif class_name == "bicycle":
                        raw_bicycles += 1
                    elif class_name == "motorcycle":
                        raw_motorcycles += 1
                    if class_name is None:
                        continue

                    conf = float(box.conf.item())
                    if class_name == "person":
                        if not person_detection_enabled or conf < person_confidence_threshold:
                            continue
                        people_after_confidence += 1
                    elif class_name == "bicycle":
                        if conf < bicycle_confidence_threshold:
                            continue
                        bicycles_after_confidence += 1
                    elif class_name not in allowed_vehicle_classes or conf < confidence_threshold:
                        continue
                    elif class_name == "motorcycle":
                        motorcycles_after_confidence += 1
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    track_id = int(box.id.item()) if box.id is not None else None
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    timestamp_sec = frame_idx / fps

                    pixel_speed = None
                    stationary_duration = None
                    if track_id is not None:
                        track_state = trajectory_manager.update(
                            track_id=track_id,
                            frame=frame_idx,
                            timestamp_sec=timestamp_sec,
                            center_x=center_x,
                            center_y=center_y,
                        )
                        pixel_speed = track_state.pixel_speed
                        stationary_duration = track_state.stationary_duration
                        if class_name == "person":
                            tracked_people += 1
                        elif class_name == "bicycle":
                            tracked_bicycles += 1
                        else:
                            current_track_states[track_id] = track_state
                            if class_name == "motorcycle":
                                tracked_motorcycles += 1

                    person_in_road = None
                    bicycle_in_road = None
                    if class_name == "person":
                        person_in_road = point_in_polygon(
                            ((x1 + x2) / 2, y2),
                            event_pipeline.congestion_rule.monitored_polygon,
                        )
                        people_in_roi += int(bool(person_in_road))
                    elif class_name == "bicycle":
                        bicycle_in_road = point_in_polygon(
                            ((x1 + x2) / 2, y2),
                            event_pipeline.congestion_rule.monitored_polygon,
                        )
                        bicycles_in_roi += int(bicycle_in_road)
                    else:
                        vehicle_observations.append(VehicleObservation(
                            center_x=center_x, center_y=center_y,
                            x1=x1, y1=y1, x2=x2, y2=y2,
                            confidence=conf, track_id=track_id, pixel_speed=pixel_speed,
                        ))
                        vehicle_count += 1

                    draw_detection(frame, x1, y1, x2, y2, class_name, track_id, conf)

                    frame_rows.append(
                        build_track_row(
                            frame_idx,
                            fps,
                            track_id,
                            class_name,
                            conf,
                            x1,
                            y1,
                            x2,
                            y2,
                            pixel_speed,
                            stationary_duration,
                            person_in_road,
                            bicycle_in_road,
                            False if class_name == "person" else None,
                        )
                    )

            mark_possible_riders(frame_rows)
            track_rows.extend(frame_rows)

            status = f"Frame {frame_idx} | Vehicles: {vehicle_count}"
            cv2.putText(
                frame,
                status,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            event_pipeline.evaluate_frame(
                timestamp=frame_idx / fps,
                tracks=list(current_track_states.values()),
                annotated_frame=frame,
                detections=vehicle_observations,
            )
            metrics = event_pipeline.congestion_rule.last_metrics
            traffic_status = (
                f"Traffic: {metrics.state.value} | ROI: {metrics.vehicles_in_roi} "
                f"| Density: {metrics.traffic_density:.3f}"
            )
            cv2.putText(
                frame,
                traffic_status,
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            writer.write(frame)
            frame_idx += 1

            if frame_idx % 30 == 0:
                pct = (frame_idx / total_frames * 100) if total_frames > 0 else 0
                print(f"  {frame_idx}/{total_frames} frames ({pct:.0f}%)")
                if debug_traffic:
                    print(
                        "  traffic "
                        f"detections={metrics.detections} "
                        f"vehicles_in_roi={metrics.vehicles_in_roi} "
                        f"tracked_vehicles={metrics.tracked_vehicles} "
                        f"density={metrics.traffic_density:.4f} "
                        f"movement={metrics.average_movement} "
                        f"candidate={metrics.congestion_candidate} "
                        f"duration={metrics.congestion_duration:.1f}s state={metrics.state.value}"
                    )
                    print(
                        "  people "
                        f"raw_person_detections={raw_people} "
                        f"people_after_confidence={people_after_confidence} "
                        f"people_in_roi={people_in_roi} tracked_people={tracked_people} "
                        f"displayed_people={people_after_confidence}"
                    )
                    print(
                        "  bicycles "
                        f"raw_bicycle_detections={raw_bicycles} "
                        f"bicycles_after_confidence={bicycles_after_confidence} "
                        f"bicycles_in_roi={bicycles_in_roi} "
                        f"tracked_bicycles={tracked_bicycles} "
                        f"displayed_bicycles={bicycles_after_confidence}"
                    )
                    print(
                        "  motorcycles "
                        f"raw={raw_motorcycles} after_confidence={motorcycles_after_confidence} "
                        f"tracked={tracked_motorcycles} displayed={motorcycles_after_confidence}"
                    )
    finally:
        cap.release()
        writer.release()

    write_tracks_csv(tracks_path, track_rows)
    events_path = event_pipeline.write_events_json()

    print(f"Done. {frame_idx} frames, {len(track_rows)} track records.")
    print(f"  Annotated video: {annotated_path}")
    print(f"  Tracks CSV:      {tracks_path}")
    print(f"  Events JSON:     {events_path} ({len(event_pipeline.events)} events)")
    return annotated_path, tracks_path, events_path


def parse_args() -> argparse.Namespace:
    ai_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="CityEye AI — detect and track road users in video"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ai_root / "config" / "camera.json",
        help="Path to camera.json config file",
    )
    parser.add_argument(
        "--video",
        type=str,
        default=None,
        help="Override video path from config (relative to ai/ or absolute)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ai_root / "output",
        help="Directory for annotated.mp4, tracks.csv, events.json, and evidence",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="YOLO weights file (default from config or yolov8n.pt)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ai_root = Path(__file__).resolve().parent

    try:
        config = load_config(args.config)
        video_path = resolve_video_path(config, ai_root, args.video)
        process_video(video_path, config, args.output_dir, args.model)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
