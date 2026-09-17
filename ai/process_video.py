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
from collections import deque
import csv
import json
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path
from math import hypot

import cv2
import numpy as np
from ultralytics import YOLO

from event_pipeline import EventPipeline
from event_rules import VehicleObservation, point_in_polygon
from frame_source import (
    CameraHealth,
    CaptureBackend,
    RTSPFrameSource,
    SourceType,
    VideoFileSource,
    mask_stream_url,
    parse_capture_backend,
    parse_source_type,
    resolve_rtsp_url,
    VLCLocalBridgeCapture,
)
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


def draw_event_debug(frame: np.ndarray, tracks: list, pipeline: EventPipeline) -> None:
    """Draw developer-only trajectory and movement diagnostics."""
    for track in tracks:
        points = [(int(item.center_x), int(item.center_y)) for item in track.history]
        if len(points) >= 2:
            cv2.polylines(
                frame, [np.asarray(points, dtype=np.int32)], False, (255, 255, 0), 2
            )
        if points:
            speed = track.smoothed_normalized_speed
            label = (
                f"#{track.track_id} nspd={speed:.4f}/s stop={track.stationary_duration:.1f}s"
                if speed is not None
                else f"#{track.track_id} nspd=n/a stop={track.stationary_duration:.1f}s"
            )
            cv2.putText(
                frame, label, (points[-1][0], max(15, points[-1][1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1, cv2.LINE_AA,
            )

    for rule in pipeline.wrong_way_rules:
        xs = [point[0] for point in rule.monitored_polygon]
        ys = [point[1] for point in rule.monitored_polygon]
        center = (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))
        dx, dy = rule.allowed_vector
        length = max(1.0, hypot(dx, dy))
        end = (
            int(center[0] + 60 * dx / length),
            int(center[1] + 60 * dy / length),
        )
        cv2.arrowedLine(frame, center, end, (255, 0, 255), 2, tipLength=0.25)
        if rule.zone_name:
            cv2.putText(
                frame, rule.zone_name, (center[0] + 4, center[1] - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 255), 1, cv2.LINE_AA,
            )
        for track in tracks:
            if len(track.history) < 2:
                continue
            first, latest = track.history[0], track.history[-1]
            if not point_in_polygon(
                (latest.center_x, latest.center_y), rule.monitored_polygon
            ):
                continue
            measured = (
                latest.center_x - first.center_x,
                latest.center_y - first.center_y,
            )
            measured_length = hypot(*measured)
            if measured_length <= 0:
                continue
            score = -(
                measured[0] * dx + measured[1] * dy
            ) / (measured_length * length)
            start = (int(first.center_x), int(first.center_y))
            finish = (int(latest.center_x), int(latest.center_y))
            cv2.arrowedLine(frame, start, finish, (0, 165, 255), 2, tipLength=0.2)
            cv2.putText(
                frame, f"opposite={max(0.0, score):.2f}",
                (finish[0] + 4, finish[1] + 14), cv2.FONT_HERSHEY_SIMPLEX,
                0.4, (0, 165, 255), 1, cv2.LINE_AA,
            )


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


def write_json_atomic(path: Path, payload: dict) -> None:
    """Publish one runtime snapshot without exposing partially-written JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", prefix=f".{path.name}.", suffix=".tmp",
            dir=path.parent, delete=False, encoding="utf-8",
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(json.dumps(payload, indent=2) + "\n")
            temporary.flush()
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_jpeg_atomic(
    path: Path, frame: np.ndarray, *, quality: int = 95, durable: bool = True
) -> None:
    """Encode and atomically publish a complete JPEG in the target directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded_ok, encoded = cv2.imencode(
        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    )
    if not encoded_ok:
        raise RuntimeError(f"Could not encode live frame: {path}")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded.tobytes())
            temporary.flush()
            if durable:
                os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class RollingRate:
    """Recent event rate that naturally falls to zero after inactivity."""

    def __init__(self, window_seconds: float = 5.0) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()

    def mark(self, timestamp: float | None = None) -> None:
        now = time.monotonic() if timestamp is None else timestamp
        self._timestamps.append(now)
        self._discard_old(now)

    def value(self, timestamp: float | None = None) -> float:
        now = time.monotonic() if timestamp is None else timestamp
        self._discard_old(now)
        return len(self._timestamps) / self.window_seconds

    def clear(self) -> None:
        self._timestamps.clear()

    def _discard_old(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()


class RawPreviewPublisher:
    """Publish source frames without blocking the VLC capture thread on JPEG I/O."""

    def __init__(self, path: Path, fps: float = 10.0) -> None:
        if fps <= 0:
            raise ValueError("preview_fps must be positive")
        self.path = path
        self.interval = 1.0 / fps
        self._last_frame_at: float | None = None
        self._tokens = 1.0
        self._condition = threading.Condition()
        self._pending: np.ndarray | None = None
        self._closed = False
        self._worker = threading.Thread(
            target=self._run, name=f"preview-{path.parent.name}", daemon=True
        )
        self._worker.start()

    def __call__(self, frame: np.ndarray, timestamp: float, _sequence: int) -> bool:
        with self._condition:
            if self._closed:
                return False
            if self._last_frame_at is not None:
                elapsed = max(0.0, timestamp - self._last_frame_at)
                # Preserve fractional publication credit so a 12 FPS source
                # can actually yield ~10 distinct preview frames. A small cap
                # tolerates DVR burst delivery without replaying old frames.
                self._tokens = min(2.0, self._tokens + elapsed / self.interval)
            self._last_frame_at = timestamp
            if self._tokens < 1.0:
                return False
            self._tokens -= 1.0
            # Keep only the newest due frame. Copying is cheap compared with
            # JPEG encoding and prevents VLC's reusable buffer from changing.
            self._pending = frame.copy()
            self._condition.notify()
            return True

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._closed:
                    self._condition.wait()
                if self._closed and self._pending is None:
                    return
                frame = self._pending
                self._pending = None
            if frame is not None:
                # Atomic replace prevents partial MJPEG reads. Preview frames
                # are ephemeral, so fsync would only add capture-side latency.
                write_jpeg_atomic(self.path, frame, quality=75, durable=False)

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._pending = None
            self._condition.notify_all()
        self._worker.join(timeout=2.0)


class LiveDetectionDiagnosticRecorder:
    """Optionally preserve live AI input frames and detector decisions for review."""

    def __init__(self, output_dir: Path, max_frames: int) -> None:
        self.output_dir = output_dir
        self.frames_dir = output_dir / "frames"
        self.max_frames = max(0, max_frames)
        self.recorded = 0
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.records_path = output_dir / "detections.jsonl"

    @property
    def active(self) -> bool:
        return self.recorded < self.max_frames

    def record(
        self,
        *,
        frame_index: int,
        timestamp: float,
        raw_frame: np.ndarray,
        boxes,
        allowed_vehicle_classes: set[str],
        confidence_threshold: float,
        person_detection_enabled: bool,
        person_confidence_threshold: float,
        bicycle_confidence_threshold: float,
        published_metrics: dict,
    ) -> None:
        if not self.active:
            return

        detections: list[dict] = []
        if boxes is not None:
            for box in boxes:
                cls_id = int(box.cls.item())
                class_name = COCO_ROAD_USER_IDS.get(cls_id)
                if class_name is None:
                    continue
                confidence = float(box.conf.item())
                if class_name == "person":
                    displayed = person_detection_enabled and confidence >= person_confidence_threshold
                    filter_reason = None if displayed else "person_confidence_or_disabled"
                elif class_name == "bicycle":
                    displayed = confidence >= bicycle_confidence_threshold
                    filter_reason = None if displayed else "bicycle_confidence"
                else:
                    displayed = (
                        class_name in allowed_vehicle_classes
                        and confidence >= confidence_threshold
                    )
                    filter_reason = None if displayed else "vehicle_class_or_confidence"
                detections.append({
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": [int(value) for value in box.xyxy[0].tolist()],
                    "track_id": int(box.id.item()) if box.id is not None else None,
                    "displayed": displayed,
                    "filter_reason": filter_reason,
                })

        frame_name = f"ai_{self.recorded:04d}_source_{frame_index}.jpg"
        write_jpeg_atomic(self.frames_dir / frame_name, raw_frame)
        record = {
            "sample_index": self.recorded,
            "source_frame_index": frame_index,
            "timestamp": timestamp,
            "frame_file": frame_name,
            "detections": detections,
            "published_metrics": published_metrics,
        }
        with self.records_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        self.recorded += 1


class VehicleClassStabilizer:
    """Keep car/bus/truck subclass metrics stable without changing track identity."""

    STABILIZED_CLASSES = frozenset({"car", "bus", "truck"})

    def __init__(self, history_size: int = 7) -> None:
        if history_size < 1:
            raise ValueError("history_size must be positive")
        self.history_size = history_size
        self._history: dict[int, deque[tuple[str, float]]] = {}

    def update(
        self,
        track_id: int | None,
        class_name: str,
        confidence: float,
    ) -> str:
        if track_id is None or class_name not in self.STABILIZED_CLASSES:
            return class_name
        history = self._history.setdefault(track_id, deque(maxlen=self.history_size))
        history.append((class_name, confidence))
        scores = {
            candidate: sum(
                score for observed, score in history if observed == candidate
            )
            for candidate in self.STABILIZED_CLASSES
        }
        return max(scores, key=scores.get)

    def expire(self, track_ids: list[int]) -> None:
        for track_id in track_ids:
            self._history.pop(track_id, None)


def source_generation_changed(previous: int | None, current: int) -> bool:
    """Signal that tracking/event temporal state must not cross a reconnect."""
    return previous is not None and previous != current


def build_live_metrics_snapshot(
    *,
    frame_idx: int,
    timestamp: float,
    generation: int,
    frame_rows: list[dict],
    traffic_state: str,
    current_track_states: dict,
) -> dict:
    """Describe only objects emitted for the current AI frame.

    Detection counts include valid untracked YOLO detections. Track counts are
    separate and only include IDs confirmed by the tracker. Historical
    class/trajectory state must never contribute an object to this snapshot.
    """
    vehicle_classes = {"car", "bus", "truck", "motorcycle"}
    current_vehicle_rows = [
        row for row in frame_rows if row["class_name"] in vehicle_classes
    ]
    active_track_ids = {
        int(row["track_id"])
        for row in frame_rows
        if row.get("track_id") is not None
    }
    return {
        "frame": frame_idx,
        "timestamp": timestamp,
        "generation": generation,
        "current_detection_count": len(frame_rows),
        "active_vehicle_count": len(current_vehicle_rows),
        "active_track_count": len(active_track_ids),
        "cars": sum(row["class_name"] == "car" for row in frame_rows),
        "buses": sum(row["class_name"] == "bus" for row in frame_rows),
        "trucks": sum(row["class_name"] == "truck" for row in frame_rows),
        "motorcycles": sum(
            row["class_name"] == "motorcycle" for row in frame_rows
        ),
        "people": sum(row["class_name"] == "person" for row in frame_rows),
        "bicycles": sum(row["class_name"] == "bicycle" for row in frame_rows),
        "traffic_state": traffic_state,
        "moving_vehicles": sum(
            state.movement_state.value == "MOVING"
            for state in current_track_states.values()
        ),
        "stationary_vehicles": sum(
            state.movement_state.value == "STATIONARY"
            for state in current_track_states.values()
        ),
        "unknown_movement_vehicles": sum(
            state.movement_state.value == "UNKNOWN"
            for state in current_track_states.values()
        ),
    }


def process_video(
    video_path: Path | None,
    config: dict,
    output_dir: Path,
    model_name: str | None = None,
    max_frames: int | None = None,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    annotated_path = output_dir / "annotated.mp4"
    tracks_path = output_dir / "tracks.csv"

    confidence_threshold = float(config.get("confidence_threshold", 0.25))
    inference_image_size = int(config.get("inference_image_size", 960))
    iou_threshold = float(config.get("iou_threshold", 0.7))
    debug_traffic = bool(config.get("debug_traffic_analysis", False))
    debug_events = bool(config.get("debug_event_analysis", False))
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
    road_polygon = config.get("monitored_road_polygon", [])
    roi_width = max(point[0] for point in road_polygon) - min(point[0] for point in road_polygon)
    roi_height = max(point[1] for point in road_polygon) - min(point[1] for point in road_polygon)
    roi_diagonal = hypot(roi_width, roi_height)
    if roi_diagonal <= 0:
        raise ValueError("monitored_road_polygon must have a positive bounding diagonal")
    stationary_speed_threshold = float(
        event_thresholds.get(
            "stopped_vehicle_max_speed_px_per_sec",
            event_thresholds.get("stopped_vehicle_max_speed_px", 3.0),
        )
    )
    def new_trajectory_manager() -> TrajectoryManager:
        return TrajectoryManager(
            history_size=int(config.get("trajectory_history_size", 30)),
            stationary_speed_threshold=stationary_speed_threshold,
            max_observation_gap_sec=float(
                config.get("trajectory_max_observation_gap_seconds", 1.0)
            ),
            movement_scale=roi_diagonal,
            stationary_normalized_speed_threshold=(
                float(event_thresholds["stopped_vehicle_max_normalized_speed_per_sec"])
                if "stopped_vehicle_max_normalized_speed_per_sec" in event_thresholds
                else None
            ),
            speed_smoothing_window=int(
                event_thresholds.get("stopped_vehicle_speed_smoothing_window", 5)
            ),
            movement_state_confirmations=int(
                config.get("vehicle_state_confirmations", 2)
            ),
            moving_hysteresis_multiplier=float(
                config.get("vehicle_state_moving_hysteresis_multiplier", 2.0)
            ),
        )

    trajectory_manager = new_trajectory_manager()
    class_stabilizer = VehicleClassStabilizer(
        int(config.get("vehicle_class_history_size", 7))
    )
    event_pipeline = EventPipeline(config=config, output_dir=output_dir)

    print(f"Loading model: {model_path}")
    model = YOLO(model_path)

    source_type = parse_source_type(config.get("source_type", "VIDEO_FILE"))
    status_path = output_dir / "camera_status.json"

    def publish_health(health: CameraHealth) -> None:
        write_json_atomic(status_path, health.to_dict())

    raw_preview: RawPreviewPublisher | None = None
    if source_type is SourceType.RTSP:
        rtsp_url = resolve_rtsp_url(config)
        capture_backend = parse_capture_backend(
            config.get("capture_backend", CaptureBackend.OPENCV.value)
        )
        print(
            f"Opening RTSP source with {capture_backend.value}: "
            f"{mask_stream_url(rtsp_url)}"
        )
        raw_preview = RawPreviewPublisher(
            output_dir / "preview.jpg", float(config.get("preview_fps", 10.0))
        )
        source = RTSPFrameSource(
            camera_id=str(config.get("camera_id", "live-camera")),
            url=rtsp_url,
            connect_timeout_seconds=float(config.get("connect_timeout", 10.0)),
            reconnect_enabled=bool(config.get("reconnect_enabled", True)),
            reconnect_delay_seconds=float(config.get("reconnect_delay_seconds", 2.0)),
            max_reconnect_delay_seconds=float(
                config.get("max_reconnect_delay_seconds", 16.0)
            ),
            stale_after_seconds=float(config.get("stale_after_seconds", 5.0)),
            capture_backend=capture_backend,
            vlc_network_caching_ms=int(config.get("vlc_network_caching_ms", 200)),
            vlc_rtsp_tcp=bool(config.get("vlc_rtsp_tcp", False)),
            status_callback=publish_health,
            frame_callback=raw_preview,
            visual_difference_threshold=float(
                config.get("visual_difference_threshold", 0.08)
            ),
            visual_stale_after_seconds=float(
                config.get("visual_stale_after_seconds", 15.0)
            ),
            visual_minimum_similar_frames=int(
                config.get("visual_minimum_similar_frames", 30)
            ),
            visual_changes_to_arm=int(config.get("visual_changes_to_arm", 3)),
        )
        target_fps = float(config.get("inference_fps", 5.0))
        if target_fps <= 0:
            raise ValueError("inference_fps must be positive")
        fps = target_fps
        total_frames = 0
        writer = None
        source_label = str(config.get("camera_id", "live-camera"))
        # Never expose a previous worker's scene while this worker connects.
        write_json_atomic(output_dir / "live_metrics.json", {
            "frame": 0,
            "timestamp": 0.0,
            "generation": 0,
            "current_detection_count": 0,
            "active_vehicle_count": 0,
            "active_track_count": 0,
            "cars": 0,
            "buses": 0,
            "trucks": 0,
            "motorcycles": 0,
            "people": 0,
            "bicycles": 0,
            "traffic_state": "UNKNOWN",
            "moving_vehicles": 0,
            "stationary_vehicles": 0,
            "unknown_movement_vehicles": 0,
        })
    else:
        if video_path is None:
            raise ValueError("video_path is required for VIDEO_FILE sources")
        source = VideoFileSource(video_path)
        fps = validate_video_metadata(source.fps, source.width, source.height)
        total_frames = source.total_frames
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(annotated_path), fourcc, fps, (source.width, source.height)
        )
        if not writer.isOpened():
            source.close()
            writer.release()
            raise RuntimeError(f"Could not create output video: {annotated_path}")
        source_label = video_path.name

    track_rows: list[dict] = []
    frame_idx = 0
    processed_frames = 0
    last_inference_at: float | None = None
    current_generation: int | None = None
    recent_processing_rate = RollingRate(
        float(config.get("processing_fps_window_seconds", 5.0))
    )
    diagnostic_recorder: LiveDetectionDiagnosticRecorder | None = None
    if source_type is SourceType.RTSP and bool(
        config.get("diagnostic_capture_enabled", False)
    ):
        diagnostic_path = Path(
            config.get("diagnostic_capture_dir", output_dir / "diagnostic_capture")
        )
        if not diagnostic_path.is_absolute():
            diagnostic_path = output_dir / diagnostic_path
        diagnostic_recorder = LiveDetectionDiagnosticRecorder(
            diagnostic_path,
            int(config.get("diagnostic_capture_max_ai_frames", 120)),
        )
        print(
            "Live AI diagnostic capture enabled: "
            f"{diagnostic_path} ({diagnostic_recorder.max_frames} AI frames maximum)"
        )

    print(
        f"Processing {source_label} ({source_type.value}, target {fps:.1f} FPS)"
    )

    try:
        while True:
            packet = source.read(timeout=1.0)
            if packet is None:
                if source_type is SourceType.VIDEO_FILE:
                    break
                continue
            if (
                source_type is SourceType.RTSP
                and last_inference_at is not None
                and packet.timestamp - last_inference_at < 1.0 / fps
            ):
                continue
            if source_generation_changed(current_generation, packet.generation):
                retained_events = event_pipeline.events
                trajectory_manager = new_trajectory_manager()
                class_stabilizer = VehicleClassStabilizer(
                    int(config.get("vehicle_class_history_size", 7))
                )
                event_pipeline = EventPipeline(config=config, output_dir=output_dir)
                event_pipeline.events = retained_events
                model = YOLO(model_path)
                recent_processing_rate.clear()
                write_json_atomic(
                    output_dir / "live_metrics.json",
                    build_live_metrics_snapshot(
                        frame_idx=packet.frame_index,
                        timestamp=packet.timestamp,
                        generation=packet.generation,
                        frame_rows=[],
                        traffic_state="UNKNOWN",
                        current_track_states={},
                    ),
                )
                print("RTSP reconnected; tracker and temporal event state reset safely.")
            current_generation = packet.generation
            last_inference_at = packet.timestamp
            raw_ai_frame = packet.frame.copy()
            frame = raw_ai_frame.copy()
            frame_idx = packet.frame_index
            timestamp_sec = packet.timestamp
            expired_track_ids = trajectory_manager.expire_stale(
                timestamp_sec,
                float(config.get("track_state_expiration_seconds", 2.0)),
            )
            class_stabilizer.expire(expired_track_ids)

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

            result_boxes = (
                results[0].boxes
                if results and results[0].boxes is not None
                else None
            )
            vehicle_count = 0
            current_track_states = {}
            vehicle_observations: list[VehicleObservation] = []
            current_track_classes: dict[int, str] = {}
            frame_rows: list[dict] = []
            raw_people = people_after_confidence = people_in_roi = tracked_people = 0
            raw_bicycles = bicycles_after_confidence = bicycles_in_roi = 0
            tracked_bicycles = 0
            raw_motorcycles = motorcycles_after_confidence = tracked_motorcycles = 0
            if result_boxes is not None and len(result_boxes) > 0:
                boxes = result_boxes
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
                    class_name = class_stabilizer.update(
                        track_id,
                        class_name,
                        conf,
                    )
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
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
                            current_track_classes[track_id] = class_name
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
                            vehicle_class=class_name,
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
            if source_type is SourceType.VIDEO_FILE:
                track_rows.extend(frame_rows)

            time_label = (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_sec))
                if source_type is SourceType.RTSP else f"{timestamp_sec:.2f}s"
            )
            status = f"Frame {frame_idx} | Time: {time_label} | Vehicles: {vehicle_count}"
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
            if debug_events:
                draw_event_debug(
                    frame,
                    list(current_track_states.values()),
                    event_pipeline,
                )
            new_events = event_pipeline.evaluate_frame(
                timestamp=timestamp_sec,
                tracks=list(current_track_states.values()),
                annotated_frame=frame,
                detections=vehicle_observations,
                track_classes=current_track_classes,
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
            if writer is not None:
                writer.write(frame)
            else:
                live_metrics_snapshot = build_live_metrics_snapshot(
                    frame_idx=frame_idx,
                    timestamp=timestamp_sec,
                    generation=packet.generation,
                    frame_rows=frame_rows,
                    traffic_state=metrics.state.value,
                    current_track_states=current_track_states,
                )
                if diagnostic_recorder is not None and diagnostic_recorder.active:
                    diagnostic_recorder.record(
                        frame_index=frame_idx,
                        timestamp=timestamp_sec,
                        raw_frame=raw_ai_frame,
                        boxes=result_boxes,
                        allowed_vehicle_classes=allowed_vehicle_classes,
                        confidence_threshold=confidence_threshold,
                        person_detection_enabled=person_detection_enabled,
                        person_confidence_threshold=person_confidence_threshold,
                        bicycle_confidence_threshold=bicycle_confidence_threshold,
                        published_metrics=live_metrics_snapshot,
                    )
                latest_path = output_dir / "latest.jpg"
                write_jpeg_atomic(latest_path, frame)
                recent_processing_rate.mark()
                source.health.processing_fps = recent_processing_rate.value()
                source.health.ai_inference_fps = recent_processing_rate.value()
                publish_health(source.health)
                write_json_atomic(
                    output_dir / "live_metrics.json",
                    live_metrics_snapshot,
                )
                if new_events:
                    event_pipeline.write_events_json()
            processed_frames += 1
            if max_frames is not None and processed_frames >= max_frames:
                break

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
        source.close()
        if raw_preview is not None:
            raw_preview.close()
        if writer is not None:
            writer.release()

    write_tracks_csv(tracks_path, track_rows)
    events_path = event_pipeline.write_events_json()

    print(f"Done. {processed_frames} frames, {len(track_rows)} track records.")
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
        "--max-frames",
        type=int,
        default=None,
        help="Stop after N inference frames (useful for live development tests)",
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
    parser.add_argument(
        "--camera-id",
        type=str,
        default=None,
        help="Override camera_id for a multi-camera live worker",
    )
    parser.add_argument(
        "--camera-name",
        type=str,
        default=None,
        help="Override camera_name for a multi-camera live worker",
    )
    return parser.parse_args()


def main() -> int:
    def graceful_shutdown(_signum, _frame) -> None:
        VLCLocalBridgeCapture.shutdown_all()
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, graceful_shutdown)
    args = parse_args()
    ai_root = Path(__file__).resolve().parent

    try:
        config = load_config(args.config)
        if args.camera_id:
            config["camera_id"] = args.camera_id
        if args.camera_name:
            config["camera_name"] = args.camera_name
        source_type = parse_source_type(config.get("source_type", "VIDEO_FILE"))
        video_path = (
            resolve_video_path(config, ai_root, args.video)
            if source_type is SourceType.VIDEO_FILE else None
        )
        process_video(
            video_path, config, args.output_dir, args.model, args.max_frames
        )
    except KeyboardInterrupt:
        print("Shutdown requested; live capture resources released.")
        return 0
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
