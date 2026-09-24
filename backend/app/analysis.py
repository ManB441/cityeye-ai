"""Read the real local AI outputs used by the Municipal Dashboard."""

from __future__ import annotations

import csv
import json
import math
from statistics import median

from pathlib import Path

from app.schemas import AnalysisFrame, AnalysisSummary, AnalysisTimeline


REQUIRED_TRACK_COLUMNS = {"frame", "track_id", "class_name"}

TIMELINE_TRACK_COLUMNS = {"frame", "timestamp_sec", "track_id", "class_name"}

VEHICLE_CLASSES = ("car", "bus", "truck", "motorcycle")


def read_analysis_summary(output_dir: Path) -> AnalysisSummary:
    """Summarize the last processed frame without inventing missing values."""

    tracks_path = output_dir / "tracks.csv"

    video_path = output_dir / "annotated.mp4"

    video_available = _is_safe_file(output_dir, video_path)

    if not _is_safe_file(output_dir, tracks_path):
        return AnalysisSummary(
            status="MISSING",
            current_vehicle_count=None,
            last_frame=None,
            total_track_records=0,
            annotated_video_available=video_available,
            message="tracks.csv is not available. Run the AI pipeline first.",
        )

    try:
        with tracks_path.open(newline="", encoding="utf-8") as tracks_file:
            reader = csv.DictReader(tracks_file)

            if (
                not reader.fieldnames
                or not REQUIRED_TRACK_COLUMNS.issubset(reader.fieldnames)
            ):
                raise ValueError("tracks.csv is missing frame or track_id")

            records = list(reader)

        parsed_frames = [int(row["frame"]) for row in records]

    except (OSError, UnicodeError, ValueError) as exc:
        return AnalysisSummary(
            status="INVALID",
            current_vehicle_count=None,
            last_frame=None,
            total_track_records=0,
            annotated_video_available=video_available,
            message=f"Unable to read tracks.csv: {exc}",
        )

    observed = read_observed_frames(output_dir)

    if not records:
        return AnalysisSummary(
            status="READY",
            current_vehicle_count=0,
            current_people_count=0,
            current_bicycle_count=0,
            last_frame=max(observed) if observed else None,
            total_track_records=0,
            annotated_video_available=video_available,
            message="The AI pipeline completed with no tracked vehicles.",
        )

    last_frame = max([*parsed_frames, *observed])

    vehicle_rows = [
        row
        for row, frame in zip(records, parsed_frames, strict=True)
        if frame == last_frame
        and row["class_name"].strip().lower() in VEHICLE_CLASSES
    ]

    people_rows = [
        row
        for row, frame in zip(records, parsed_frames, strict=True)
        if frame == last_frame
        and row["class_name"].strip().lower() == "person"
    ]

    bicycle_rows = [
        row
        for row, frame in zip(records, parsed_frames, strict=True)
        if frame == last_frame
        and row["class_name"].strip().lower() == "bicycle"
    ]

    current_ids = {
        row["track_id"].strip()
        for row in vehicle_rows
        if row["track_id"].strip()
    }

    unassigned_detections = sum(
        1 for row in vehicle_rows if not row["track_id"].strip()
    )

    return AnalysisSummary(
        status="READY",
        current_vehicle_count=len(current_ids) + unassigned_detections,
        current_people_count=len(people_rows),
        current_bicycle_count=len(bicycle_rows),
        last_frame=last_frame,
        total_track_records=len(records),
        annotated_video_available=video_available,
        message="Summary calculated from the real tracks.csv output.",
    )


def resolve_annotated_video(output_dir: Path) -> Path | None:
    """Return the fixed annotated MP4 only when it remains inside output_dir."""

    video_path = output_dir / "annotated.mp4"

    return (
        video_path.resolve()
        if _is_safe_file(output_dir, video_path)
        else None
    )


def read_traffic_timeline(output_dir: Path) -> dict[int, str]:
    """
    Read the AI-computed traffic state for each processed frame.

    The AI pipeline writes this data to traffic_timeline.json.

    Expected format:

    {
        "frames": [
            {
                "frame": 0,
                "timestamp_sec": 0.0,
                "traffic_state": "NORMAL"
            }
        ]
    }

    Missing or invalid traffic timeline data is intentionally treated
    as unavailable rather than making the entire analysis timeline invalid.
    """

    traffic_timeline_path = output_dir / "traffic_timeline.json"

    if not _is_safe_file(output_dir, traffic_timeline_path):
        return {}

    try:
        with traffic_timeline_path.open(
            encoding="utf-8"
        ) as timeline_file:
            payload = json.load(timeline_file)

        if not isinstance(payload, dict):
            return {}

        raw_frames = payload.get("frames")

        if not isinstance(raw_frames, list):
            return {}

        traffic_by_frame: dict[int, str] = {}

        for item in raw_frames:
            if not isinstance(item, dict):
                continue

            try:
                frame_number = int(item["frame"])
            except (KeyError, TypeError, ValueError):
                continue

            traffic_state = str(
                item.get("traffic_state", "UNKNOWN")
            ).strip().upper()

            if not traffic_state:
                traffic_state = "UNKNOWN"

            traffic_by_frame[frame_number] = traffic_state

        return traffic_by_frame

    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return {}


def read_observed_frames(output_dir: Path) -> dict[int, float]:
    """Only the processed-frame manifest establishes an observation with no rows.

    Never fill arbitrary CSV gaps: those may be unprocessed frames.
    """
    path = output_dir / "traffic_timeline.json"
    if not _is_safe_file(output_dir, path):
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload["frames"]
        if not isinstance(items, list):
            return {}
        observed: dict[int, float] = {}
        for item in items:
            number = item["frame"]
            timestamp = item["timestamp_sec"]
            if (type(number) is not int or number < 0
                    or type(timestamp) not in (int, float)
                    or not math.isfinite(timestamp) or timestamp < 0
                    or number in observed):
                return {}
            observed[number] = float(timestamp)
        ordered = sorted(observed)
        if any(observed[b] <= observed[a] for a, b in zip(ordered, ordered[1:])):
            return {}
        return observed
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return {}


def read_analysis_timeline(output_dir: Path) -> AnalysisTimeline:
    """
    Return real per-frame class counts from tracks.csv.

    Traffic state is read from the AI-generated traffic_timeline.json
    and attached to the corresponding AnalysisFrame.
    """

    tracks_path = output_dir / "tracks.csv"

    if not _is_safe_file(output_dir, tracks_path):
        return AnalysisTimeline(
            status="MISSING",
            frames=[],
            message="tracks.csv is not available. Run the AI pipeline first.",
        )

    traffic_by_frame = read_traffic_timeline(output_dir)

    try:
        with tracks_path.open(
            newline="",
            encoding="utf-8",
        ) as tracks_file:
            reader = csv.DictReader(tracks_file)

            if (
                not reader.fieldnames
                or not TIMELINE_TRACK_COLUMNS.issubset(reader.fieldnames)
            ):
                raise ValueError("tracks.csv is missing timeline columns")

            grouped: dict[int, list[dict[str, str]]] = {}

            for row in reader:
                grouped.setdefault(
                    int(row["frame"]),
                    [],
                ).append(row)

        observed = read_observed_frames(output_dir)
        timestamps = {number: float(rows[0]["timestamp_sec"]) for number, rows in grouped.items()}
        timestamps.update(observed)
        ordered = sorted(timestamps)
        intervals = [(timestamps[b] - timestamps[a]) / (b - a)
                     for a, b in zip(ordered, ordered[1:])
                     if timestamps[b] > timestamps[a]]
        duration = round(median(intervals), 6) if intervals else None
        frames: list[AnalysisFrame] = []

        for frame_number in ordered:
            rows = grouped.get(frame_number, [])

            unique_tracks: dict[str, str] = {}

            unassigned: list[str] = []

            for row in rows:
                class_name = row["class_name"].strip().lower()

                track_id = row["track_id"].strip()

                if track_id:
                    unique_tracks.setdefault(
                        track_id,
                        class_name,
                    )
                else:
                    unassigned.append(class_name)

            classes = list(unique_tracks.values()) + unassigned

            counts = {
                name: classes.count(name)
                for name in VEHICLE_CLASSES
            }

            people_rows = [
                row
                for row in rows
                if row["class_name"].strip().lower() == "person"
            ]

            bicycle_rows = [
                row
                for row in rows
                if row["class_name"].strip().lower() == "bicycle"
            ]

            people_in_road = sum(
                row.get(
                    "person_in_road",
                    "",
                ).strip().lower()
                == "true"
                for row in people_rows
            )

            bicycles_in_road = sum(
                row.get(
                    "bicycle_in_road",
                    "",
                ).strip().lower()
                == "true"
                for row in bicycle_rows
            )

            traffic_state = traffic_by_frame.get(
                frame_number,
                "UNKNOWN",
            )

            frames.append(
                AnalysisFrame(
                    frame=frame_number,
                    timestamp_sec=timestamps[frame_number],
                    duration_sec=duration,
                    traffic_state=traffic_state,
                    active_vehicle_count=sum(
                        counts.values()
                    ),
                    cars=counts["car"],
                    buses=counts["bus"],
                    trucks=counts["truck"],
                    motorcycles=counts["motorcycle"],
                    people=len(people_rows),
                    people_in_road=people_in_road,
                    tracked_people=sum(
                        bool(row["track_id"].strip())
                        for row in people_rows
                    ),
                    bicycles=len(bicycle_rows),
                    bicycles_in_road=bicycles_in_road,
                    tracked_bicycles=sum(
                        bool(row["track_id"].strip())
                        for row in bicycle_rows
                    ),
                )
            )

    except (
        OSError,
        UnicodeError,
        ValueError,
    ) as exc:
        return AnalysisTimeline(
            status="INVALID",
            frames=[],
            message=f"Unable to read tracks.csv: {exc}",
        )

    return AnalysisTimeline(
        status="READY",
        frames=frames,
        message=(
            "Timeline calculated from real YOLO and ByteTrack "
            "output with AI traffic state."
        ),
    )


def _is_safe_file(output_dir: Path, candidate: Path) -> bool:
    output_root = output_dir.resolve()

    resolved = candidate.resolve()

    return resolved.parent == output_root and resolved.is_file()