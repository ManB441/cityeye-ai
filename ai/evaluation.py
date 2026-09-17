"""Repeatable, ground-truth-aware evaluation helpers for CityEye AI.

This module is intentionally separate from the production video pipeline.  It
can inspect existing outputs and benchmark representative source frames without
changing production model weights or thresholds.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable

import cv2
import numpy as np
from ultralytics import YOLO

from event_rules import CongestionRule, VehicleObservation, point_in_polygon
from process_video import COCO_ROAD_USER_IDS, load_config, resolve_model_reference


ROAD_USER_CLASSES = tuple(COCO_ROAD_USER_IDS.values())
VEHICLE_CLASSES = ("car", "motorcycle", "bus", "truck")


@dataclass(frozen=True)
class Detection:
    class_name: str
    confidence: float
    box: tuple[float, float, float, float]
    track_id: int | None = None

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) / 2, (y1 + y2) / 2)


@dataclass(frozen=True)
class QualityMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float | None
    recall: float | None


@dataclass(frozen=True)
class BenchmarkVariant:
    name: str
    model: str
    imgsz: int
    raw_confidence: float
    use_road_crop: bool = False


def intersection_over_union(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    """Return bounding-box IoU in the inclusive range [0, 1]."""
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = width * height
    first_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    second_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = first_area + second_area - intersection
    return 0.0 if union <= 0 else intersection / union


def calculate_detection_quality(
    predictions: Iterable[Detection],
    ground_truth: Iterable[Detection],
    iou_threshold: float = 0.5,
) -> QualityMetrics:
    """Greedily match same-class boxes and calculate TP, FP, FN, precision/recall."""
    if not 0 < iou_threshold <= 1:
        raise ValueError("iou_threshold must be between 0 and 1")
    predictions = list(predictions)
    ground_truth = list(ground_truth)
    candidates: list[tuple[float, int, int]] = []
    for prediction_index, prediction in enumerate(predictions):
        for truth_index, truth in enumerate(ground_truth):
            if prediction.class_name != truth.class_name:
                continue
            score = intersection_over_union(prediction.box, truth.box)
            if score >= iou_threshold:
                candidates.append((score, prediction_index, truth_index))
    matched_predictions: set[int] = set()
    matched_truth: set[int] = set()
    for _, prediction_index, truth_index in sorted(candidates, reverse=True):
        if prediction_index in matched_predictions or truth_index in matched_truth:
            continue
        matched_predictions.add(prediction_index)
        matched_truth.add(truth_index)
    true_positive = len(matched_predictions)
    false_positive = len(predictions) - true_positive
    false_negative = len(ground_truth) - true_positive
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    return QualityMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=(true_positive / precision_denominator if precision_denominator else None),
        recall=(true_positive / recall_denominator if recall_denominator else None),
    )


def production_threshold(config: dict, class_name: str) -> float:
    if class_name == "person":
        return float(config.get("person_confidence_threshold", 0.22))
    if class_name == "bicycle":
        return float(config.get("bicycle_confidence_threshold", 0.22))
    return float(config.get("confidence_threshold", 0.25))


def filter_detections(detections: Iterable[Detection], config: dict) -> list[Detection]:
    allowed_vehicles = set(config.get("vehicle_classes", VEHICLE_CLASSES))
    people_enabled = bool(config.get("person_detection_enabled", True))
    accepted = []
    for detection in detections:
        if detection.class_name == "person" and not people_enabled:
            continue
        if detection.class_name not in {"person", "bicycle", *allowed_vehicles}:
            continue
        if detection.confidence >= production_threshold(config, detection.class_name):
            accepted.append(detection)
    return accepted


def detections_in_roi(
    detections: Iterable[Detection], polygon: list[tuple[float, float]]
) -> list[Detection]:
    return [item for item in detections if point_in_polygon(item.center, polygon)]


def class_counts(detections: Iterable[Detection]) -> dict[str, int]:
    counts = Counter(item.class_name for item in detections)
    return {class_name: counts[class_name] for class_name in ROAD_USER_CLASSES}


def road_crop(
    frame: np.ndarray, polygon: list[tuple[float, float]]
) -> tuple[np.ndarray, tuple[int, int]]:
    """Crop to the clamped bounding rectangle of the configured road polygon."""
    height, width = frame.shape[:2]
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    x1 = max(0, min(width - 1, int(min(xs))))
    y1 = max(0, min(height - 1, int(min(ys))))
    x2 = max(x1 + 1, min(width, int(max(xs))))
    y2 = max(y1 + 1, min(height, int(max(ys))))
    return frame[y1:y2, x1:x2], (x1, y1)


def extract_detections(result: object, offset: tuple[int, int] = (0, 0)) -> list[Detection]:
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return []
    offset_x, offset_y = offset
    extracted = []
    for box in boxes:
        class_id = int(box.cls.item())
        class_name = COCO_ROAD_USER_IDS.get(class_id)
        if class_name is None:
            continue
        x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
        extracted.append(
            Detection(
                class_name=class_name,
                confidence=float(box.conf.item()),
                box=(x1 + offset_x, y1 + offset_y, x2 + offset_x, y2 + offset_y),
                track_id=int(box.id.item()) if box.id is not None else None,
            )
        )
    return extracted


def read_frame(video_path: Path, timestamp: float) -> tuple[np.ndarray, int, float]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps <= 0:
        fps = 25.0
    capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
    ok, frame = capture.read()
    frame_index = int(round(timestamp * fps))
    capture.release()
    if not ok:
        raise ValueError(f"Could not read {video_path.name} at {timestamp:.3f}s")
    return frame, frame_index, fps


def export_annotation_frames(
    scenario: str,
    video_path: Path,
    frame_indices: list[int],
    output_dir: Path,
) -> list[dict]:
    """Export exact clean source frames and return reproducibility metadata."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps <= 0:
        capture.release()
        raise RuntimeError(f"Video has invalid FPS metadata: {video_path}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    scenario_dir = output_dir / scenario
    scenario_dir.mkdir(parents=True, exist_ok=True)
    exported = []
    for frame_index in frame_indices:
        if not 0 <= frame_index < total_frames:
            capture.release()
            raise ValueError(
                f"Frame {frame_index} is outside {video_path.name} "
                f"(0-{total_frames - 1})"
            )
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            capture.release()
            raise RuntimeError(f"Could not decode frame {frame_index}: {video_path}")
        filename = f"{scenario}__{video_path.stem}__frame_{frame_index:06d}.png"
        destination = scenario_dir / filename
        if not cv2.imwrite(str(destination), frame):
            capture.release()
            raise RuntimeError(f"Could not write annotation frame: {destination}")
        exported.append({
            "scenario": scenario,
            "source_video": video_path.name,
            "source_video_path": str(video_path),
            "frame_index": frame_index,
            "timestamp_sec": round(frame_index / fps, 6),
            "width": width,
            "height": height,
            "image": str(destination),
        })
    capture.release()
    return exported


def benchmark_variant(
    model: YOLO,
    frame: np.ndarray,
    config: dict,
    variant: BenchmarkVariant,
) -> dict:
    polygon = [tuple(point) for point in config["monitored_road_polygon"]]
    inference_frame, offset = (road_crop(frame, polygon) if variant.use_road_crop else (frame, (0, 0)))
    started = time.perf_counter()
    results = model.predict(
        inference_frame,
        conf=variant.raw_confidence,
        imgsz=variant.imgsz,
        iou=float(config.get("iou_threshold", 0.7)),
        classes=list(COCO_ROAD_USER_IDS),
        verbose=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    raw = extract_detections(results[0], offset) if results else []
    filtered = filter_detections(raw, config)
    inside_roi = detections_in_roi(filtered, polygon)
    vehicle_observations = [
        VehicleObservation(
            center_x=item.center[0], center_y=item.center[1],
            x1=item.box[0], y1=item.box[1], x2=item.box[2], y2=item.box[3],
            confidence=item.confidence, track_id=item.track_id,
        )
        for item in filtered if item.class_name in VEHICLE_CLASSES
    ]
    thresholds = config.get("event_thresholds", {})
    rule = CongestionRule(
        monitored_polygon=polygon,
        min_vehicles=int(thresholds.get("congestion_min_vehicles", 16)),
        moderate_min_vehicles=int(thresholds.get("congestion_moderate_min_vehicles", min(12, int(thresholds.get("congestion_min_vehicles", 16))))),
        min_density=float(thresholds.get("congestion_min_density", 0.04)),
        max_spacing=float(thresholds.get("congestion_max_normalized_spacing", 0.12)),
        max_movement=float(thresholds.get("congestion_max_normalized_movement", 0.12)),
        min_detection_confidence=float(thresholds.get("congestion_min_detection_confidence", 0.3)),
        min_duration_seconds=float(thresholds.get("congestion_duration_seconds", 5.0)),
    )
    metrics = rule.calculate_metrics(0.0, vehicle_observations)
    return {
        "raw_detections": len(raw),
        "after_confidence_filter": len(filtered),
        "after_roi": len(inside_roi),
        "raw_class_counts": class_counts(raw),
        "filtered_class_counts": class_counts(filtered),
        "roi_class_counts": class_counts(inside_roi),
        "tracked_objects": sum(item.track_id is not None for item in filtered),
        "traffic_density": metrics.traffic_density,
        "traffic_state": metrics.state.value,
        "congestion_candidate": metrics.congestion_candidate,
        "inference_ms": round(elapsed_ms, 3),
        "fps": round(1000 / elapsed_ms, 3) if elapsed_ms > 0 else None,
        "detections": [asdict(item) for item in filtered],
    }


def load_ground_truth(path: Path | None) -> dict[tuple[str, int], list[Detection]]:
    """Load explicit manual annotations; an absent file means no quality claims."""
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    annotations: dict[tuple[str, int], list[Detection]] = defaultdict(list)
    for frame in payload.get("frames", []):
        key = (str(frame["video"]), int(frame["frame_index"]))
        for item in frame.get("annotations", []):
            annotations[key].append(
                Detection(str(item["class_name"]), 1.0, tuple(map(float, item["box"])))
            )
    return dict(annotations)


def summarize_existing_tracks(output_dir: Path, config_path: Path | None = None) -> dict:
    """Summarize current production CSV output without rerunning inference."""
    tracks_path = output_dir / "tracks.csv"
    events_path = output_dir / "events.json"
    config = load_config(config_path) if config_path else None
    polygon = (
        [tuple(point) for point in config["monitored_road_polygon"]]
        if config is not None
        else None
    )
    by_frame: dict[int, list[dict[str, str]]] = defaultdict(list)
    with tracks_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            by_frame[int(row["frame"])].append(row)
    frame_summaries = []
    polygon_counts = Counter()
    for frame_index, rows in sorted(by_frame.items()):
        counts = Counter(row["class_name"] for row in rows)
        tracked = {row["track_id"] for row in rows if row["track_id"]}
        vehicles_in_roi = None
        if polygon is not None:
            vehicles_in_roi = sum(
                row["class_name"] in VEHICLE_CLASSES
                and point_in_polygon(
                    (
                        (float(row["x1"]) + float(row["x2"])) / 2,
                        (float(row["y1"]) + float(row["y2"])) / 2,
                    ),
                    polygon,
                )
                for row in rows
            )
        people_in_roi = sum(row.get("person_in_road", "").lower() == "true" for row in rows)
        bicycles_in_roi = sum(row.get("bicycle_in_road", "").lower() == "true" for row in rows)
        frame_summaries.append({
            "frame_index": frame_index,
            "timestamp": float(rows[0]["timestamp_sec"]),
            "detections": len(rows),
            "class_counts": {name: counts[name] for name in ROAD_USER_CLASSES},
            "tracked_objects": len(tracked),
            "vehicles_in_roi": vehicles_in_roi,
            "people_in_roi": people_in_roi,
            "bicycles_in_roi": bicycles_in_roi,
        })
    events = json.loads(events_path.read_text(encoding="utf-8")) if events_path.exists() else []
    return {
        "output_dir": str(output_dir),
        "config": str(config_path) if config_path else None,
        "frame_count_with_detections": len(frame_summaries),
        "frames": frame_summaries,
        "events": events,
    }


def default_variants(config: dict) -> list[BenchmarkVariant]:
    production_imgsz = int(config.get("inference_image_size", 960))
    production_raw_conf = min(
        float(config.get("confidence_threshold", 0.25)),
        float(config.get("person_confidence_threshold", 0.22)),
        float(config.get("bicycle_confidence_threshold", 0.22)),
    )
    return [
        BenchmarkVariant("A-production", str(config.get("model", "yolov8n.pt")), production_imgsz, production_raw_conf),
        BenchmarkVariant("B-yolov8n-1280-low-conf", str(config.get("model", "yolov8n.pt")), 1280, 0.05),
        BenchmarkVariant("C-yolov8s-1280-full", "yolov8s.pt", 1280, 0.05),
        BenchmarkVariant("D-yolov8s-1280-road-crop", "yolov8s.pt", 1280, 0.05, True),
    ]


def run_benchmark(
    video_path: Path,
    config_path: Path,
    timestamps: list[float],
    output_path: Path,
    ground_truth_path: Path | None = None,
    variant_names: set[str] | None = None,
) -> dict:
    config = load_config(config_path)
    ai_root = Path(__file__).resolve().parent
    ground_truth = load_ground_truth(ground_truth_path)
    variants = [
        variant for variant in default_variants(config)
        if variant_names is None or variant.name in variant_names
    ]
    if not variants:
        raise ValueError("No benchmark variants selected")
    models: dict[str, YOLO] = {}
    warmed_inference_shapes: set[tuple[str, int, int, int]] = set()
    report = {"video": str(video_path), "config": str(config_path), "frames": []}
    for timestamp in timestamps:
        frame, frame_index, fps = read_frame(video_path, timestamp)
        frame_report = {"timestamp": timestamp, "frame_index": frame_index, "source_fps": fps, "variants": []}
        for variant in variants:
            if variant.model not in models:
                model_reference = resolve_model_reference(variant.model, ai_root)
                models[variant.model] = YOLO(model_reference)
            model = models[variant.model]
            polygon = [tuple(point) for point in config["monitored_road_polygon"]]
            inference_frame = road_crop(frame, polygon)[0] if variant.use_road_crop else frame
            warmup_key = (
                variant.model,
                variant.imgsz,
                inference_frame.shape[0],
                inference_frame.shape[1],
            )
            if warmup_key not in warmed_inference_shapes:
                model.predict(
                    inference_frame,
                    conf=variant.raw_confidence,
                    imgsz=variant.imgsz,
                    iou=float(config.get("iou_threshold", 0.7)),
                    classes=list(COCO_ROAD_USER_IDS),
                    verbose=False,
                )
                warmed_inference_shapes.add(warmup_key)
            result = benchmark_variant(model, frame, config, variant)
            truth = ground_truth.get((video_path.name, frame_index))
            result["quality"] = (
                asdict(calculate_detection_quality(
                    [Detection(item["class_name"], item["confidence"], tuple(item["box"]), item["track_id"]) for item in result["detections"]],
                    truth,
                )) if truth is not None else None
            )
            result["variant"] = asdict(variant)
            frame_report["variants"].append(result)
        report["frames"].append(frame_report)
    for variant in variants:
        timings = [
            item["inference_ms"] for frame in report["frames"] for item in frame["variants"]
            if item["variant"]["name"] == variant.name
        ]
        report.setdefault("performance", {})[variant.name] = {
            "average_inference_ms": round(mean(timings), 3),
            "approximate_fps": round(1000 / mean(timings), 3),
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    outputs = subparsers.add_parser("outputs", help="Summarize an existing tracks.csv/events.json output")
    outputs.add_argument("output_dir", type=Path)
    outputs.add_argument("--config", type=Path)
    outputs.add_argument("--json", type=Path)
    benchmark = subparsers.add_parser("benchmark", help="Benchmark representative video frames")
    benchmark.add_argument("--video", type=Path, required=True)
    benchmark.add_argument("--config", type=Path, required=True)
    benchmark.add_argument("--timestamps", type=float, nargs="+", required=True)
    benchmark.add_argument("--output", type=Path, required=True)
    benchmark.add_argument("--ground-truth", type=Path)
    benchmark.add_argument(
        "--variants",
        nargs="+",
        choices=[variant.name for variant in default_variants({})],
        help="Run only the selected variants (default: all)",
    )
    export = subparsers.add_parser(
        "export-frames", help="Export clean source frames for manual annotation"
    )
    export.add_argument("--scenario", required=True)
    export.add_argument("--video", type=Path, required=True)
    export.add_argument("--frames", type=int, nargs="+", required=True)
    export.add_argument("--output-dir", type=Path, required=True)
    export.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "outputs":
        report = summarize_existing_tracks(args.output_dir, args.config)
        rendered = json.dumps(report, indent=2)
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    if args.command == "export-frames":
        entries = export_annotation_frames(
            args.scenario, args.video, args.frames, args.output_dir
        )
        existing = []
        if args.manifest.exists():
            existing = json.loads(args.manifest.read_text(encoding="utf-8")).get(
                "frames", []
            )
        keys = {(item["scenario"], item["frame_index"]) for item in entries}
        merged = [
            item for item in existing
            if (item["scenario"], item["frame_index"]) not in keys
        ] + entries
        merged.sort(key=lambda item: (item["scenario"], item["frame_index"]))
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps({"version": 1, "frames": merged}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Exported {len(entries)} frames to {args.output_dir}")
        return 0
    run_benchmark(
        args.video,
        args.config,
        args.timestamps,
        args.output,
        args.ground_truth,
        set(args.variants) if args.variants else None,
    )
    print(f"Wrote benchmark report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
