"""Read the real local AI outputs used by the Municipal Dashboard."""

from __future__ import annotations

import csv
from pathlib import Path

from app.schemas import AnalysisFrame, AnalysisSummary, AnalysisTimeline


REQUIRED_TRACK_COLUMNS = {"frame", "track_id"}
TIMELINE_TRACK_COLUMNS = {"frame", "timestamp_sec", "track_id", "class_name"}
VEHICLE_CLASSES = ("car", "bus", "truck", "motorcycle")


def read_analysis_summary(output_dir: Path) -> AnalysisSummary:
    """Summarize the last processed frame without inventing missing values."""
    tracks_path = output_dir / "tracks.csv"
    video_path = output_dir / "annotated.mp4"
    video_available = _is_safe_file(output_dir, video_path)
    if not _is_safe_file(output_dir, tracks_path):
        return AnalysisSummary(
            status="MISSING", current_vehicle_count=None, last_frame=None,
            total_track_records=0, annotated_video_available=video_available,
            message="tracks.csv is not available. Run the AI pipeline first.",
        )
    try:
        with tracks_path.open(newline="", encoding="utf-8") as tracks_file:
            reader = csv.DictReader(tracks_file)
            if not reader.fieldnames or not REQUIRED_TRACK_COLUMNS.issubset(reader.fieldnames):
                raise ValueError("tracks.csv is missing frame or track_id")
            records = list(reader)
        parsed_frames = [int(row["frame"]) for row in records]
    except (OSError, UnicodeError, ValueError) as exc:
        return AnalysisSummary(
            status="INVALID", current_vehicle_count=None, last_frame=None,
            total_track_records=0, annotated_video_available=video_available,
            message=f"Unable to read tracks.csv: {exc}",
        )
    if not records:
        return AnalysisSummary(
            status="READY", current_vehicle_count=0, last_frame=None,
            total_track_records=0, annotated_video_available=video_available,
            message="The AI pipeline completed with no tracked vehicles.",
        )
    last_frame = max(parsed_frames)
    current_ids = {
        row["track_id"].strip()
        for row, frame in zip(records, parsed_frames, strict=True)
        if frame == last_frame and row["track_id"].strip()
    }
    unassigned_detections = sum(
        1
        for row, frame in zip(records, parsed_frames, strict=True)
        if frame == last_frame and not row["track_id"].strip()
    )
    return AnalysisSummary(
        status="READY",
        current_vehicle_count=len(current_ids) + unassigned_detections,
        last_frame=last_frame,
        total_track_records=len(records), annotated_video_available=video_available,
        message="Summary calculated from the real tracks.csv output.",
    )


def resolve_annotated_video(output_dir: Path) -> Path | None:
    """Return the fixed annotated MP4 only when it remains inside output_dir."""
    video_path = output_dir / "annotated.mp4"
    return video_path.resolve() if _is_safe_file(output_dir, video_path) else None


def read_analysis_timeline(output_dir: Path) -> AnalysisTimeline:
    """Return real per-frame class counts from tracks.csv without interpolation."""
    tracks_path = output_dir / "tracks.csv"
    if not _is_safe_file(output_dir, tracks_path):
        return AnalysisTimeline(
            status="MISSING", frames=[],
            message="tracks.csv is not available. Run the AI pipeline first.",
        )
    try:
        with tracks_path.open(newline="", encoding="utf-8") as tracks_file:
            reader = csv.DictReader(tracks_file)
            if not reader.fieldnames or not TIMELINE_TRACK_COLUMNS.issubset(reader.fieldnames):
                raise ValueError("tracks.csv is missing timeline columns")
            grouped: dict[int, list[dict[str, str]]] = {}
            for row in reader:
                grouped.setdefault(int(row["frame"]), []).append(row)

        frames: list[AnalysisFrame] = []
        for frame_number in sorted(grouped):
            rows = grouped[frame_number]
            unique_tracks: dict[str, str] = {}
            unassigned: list[str] = []
            for row in rows:
                class_name = row["class_name"].strip().lower()
                track_id = row["track_id"].strip()
                if track_id:
                    unique_tracks.setdefault(track_id, class_name)
                else:
                    unassigned.append(class_name)
            classes = list(unique_tracks.values()) + unassigned
            counts = {name: classes.count(name) for name in VEHICLE_CLASSES}
            frames.append(AnalysisFrame(
                frame=frame_number,
                timestamp_sec=float(rows[0]["timestamp_sec"]),
                active_vehicle_count=len(classes),
                cars=counts["car"], buses=counts["bus"],
                trucks=counts["truck"], motorcycles=counts["motorcycle"],
            ))
    except (OSError, UnicodeError, ValueError) as exc:
        return AnalysisTimeline(status="INVALID", frames=[], message=f"Unable to read tracks.csv: {exc}")
    return AnalysisTimeline(
        status="READY", frames=frames,
        message="Timeline calculated from real YOLO and ByteTrack output.",
    )


def _is_safe_file(output_dir: Path, candidate: Path) -> bool:
    output_root = output_dir.resolve()
    resolved = candidate.resolve()
    return resolved.parent == output_root and resolved.is_file()
