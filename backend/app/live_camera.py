"""Read sanitized live-camera snapshots produced by the AI worker."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time
from typing import Callable, Iterator

from pydantic import ValidationError

from app.schemas import CameraHealthResponse, LiveMetricsResponse, LiveMetricsSnapshot


def read_camera_health(
    directory: Path,
    *,
    clock=time.time,
    stale_after_seconds: float | None = None,
) -> CameraHealthResponse:
    path = directory / "camera_status.json"
    if not path.is_file():
        return CameraHealthResponse(
            camera_id="live-camera",
            source_type="RTSP",
            state="OFFLINE",
            last_error="Live AI worker has not published camera status.",
        )
    try:
        health = CameraHealthResponse.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        threshold = stale_after_seconds
        if threshold is None:
            threshold = float(os.getenv("CITYEYE_LIVE_STATUS_STALE_SECONDS", "10"))
        now = clock()
        heartbeat = health.heartbeat_at or health.last_frame_at
        age = now - heartbeat if heartbeat is not None else float("inf")
        if (
            health.state in {"ONLINE", "STALE", "RECONNECTING"}
            and (
                heartbeat is None
                or not math.isfinite(age) or age < 0 or age >= threshold
            )
        ):
            return health.model_copy(update={
                "state": "OFFLINE",
                "processing_fps": 0.0,
                "ai_inference_fps": 0.0,
                "camera_capture_fps": 0.0,
                "preview_publication_fps": 0.0,
                "last_error": "Live worker heartbeat is stale or stopped.",
            })
        return health.model_copy(update={"checked_at": now, "valid_for_seconds": max(0.0, threshold - age) if math.isfinite(age) and age >= 0 else 0.0})
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        raise ValueError("Live camera status is invalid") from exc


def read_live_metrics(directory: Path) -> LiveMetricsResponse:
    path = directory / "live_metrics.json"
    if not path.is_file():
        return LiveMetricsResponse()
    try:
        return LiveMetricsResponse.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        raise ValueError("Live camera metrics are invalid") from exc


DEFAULT_AI_MAX_AGE_SECONDS = 5.0


def read_live_snapshot(directory: Path, camera_id: str, *, clock=time.time) -> LiveMetricsSnapshot:
    """One freshness rule for UI, AI streams and analytics; no cross-source fallback."""
    maximum = float(os.getenv("CITYEYE_LIVE_AI_MAX_AGE_SECONDS", str(DEFAULT_AI_MAX_AGE_SECONDS)))
    if not math.isfinite(maximum) or not 0 < maximum <= 10:
        raise ValueError("CITYEYE_LIVE_AI_MAX_AGE_SECONDS must be greater than 0 and at most 10")
    metrics = None
    reason = "MISSING"
    try:
        path = directory / "live_metrics.json"
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            required = set(LiveMetricsResponse.model_fields) - {"camera_id"}
            if not isinstance(payload, dict) or not required.issubset(payload):
                raise ValueError("Incomplete live observation")
            metrics = LiveMetricsResponse.model_validate(payload)
            reason = "FRESH"
    except (OSError, ValueError, ValidationError):
        reason = "INVALID"
    # Read health AFTER metrics: a reconnect must invalidate the older observation.
    try:
        health = read_camera_health(directory, clock=clock)
    except ValueError:
        health = CameraHealthResponse(camera_id=camera_id)
    now = clock()
    budget = 0.0
    if health.camera_id != camera_id:
        reason = "SOURCE_MISMATCH"
    elif health.state != "ONLINE" or health.valid_for_seconds <= 0:
        reason = "OFFLINE"
    elif metrics is not None:
        if metrics.camera_id is not None and metrics.camera_id != camera_id:
            reason = "SOURCE_MISMATCH"
        elif metrics.generation != health.generation:
            reason = "GENERATION_MISMATCH"
        elif metrics.timestamp <= 0 or metrics.timestamp > now:
            reason = "INVALID"
        elif health.last_connected_at is not None and metrics.timestamp < health.last_connected_at:
            reason = "GENERATION_MISMATCH"
        elif now - metrics.timestamp >= maximum:
            reason = "STALE"
        else:
            budget = min(maximum - (now - metrics.timestamp), health.valid_for_seconds)
    return LiveMetricsSnapshot(
        camera_id=camera_id, checked_at=now, max_age_seconds=maximum,
        valid_for_seconds=budget if reason == "FRESH" else 0,
        reason=reason, health=health, metrics=metrics if reason == "FRESH" else None,
    )


def mjpeg_frames(
    directory: Path, poll_seconds: float = 0.01, filename: str = "latest.jpg",
    is_current: Callable[[], bool] | None = None
) -> Iterator[bytes]:
    """Yield each newly-published annotated JPG as a multipart MJPEG frame."""
    path = directory / filename
    last_modified = -1
    next_check = 0.0
    while True:
        if is_current is not None and time.monotonic() >= next_check:
            if not is_current():
                return
            next_check = time.monotonic() + 0.25
        try:
            modified = path.stat().st_mtime_ns
            if modified != last_modified:
                image = path.read_bytes()
                if image.startswith(b"\xff\xd8") and image.endswith(b"\xff\xd9"):
                    last_modified = modified
                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(image)}\r\n\r\n".encode()
                        + image
                        + b"\r\n"
                    )
        except FileNotFoundError:
            pass
        time.sleep(poll_seconds)
