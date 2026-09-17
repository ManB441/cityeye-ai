"""Read sanitized live-camera snapshots produced by the AI worker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Iterator

from pydantic import ValidationError

from app.schemas import CameraHealthResponse, LiveMetricsResponse


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
        heartbeat = health.heartbeat_at or health.last_frame_at
        if (
            health.state in {"ONLINE", "STALE", "RECONNECTING"}
            and (
                heartbeat is None
                or clock() - heartbeat > threshold
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
        return health
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


def mjpeg_frames(
    directory: Path, poll_seconds: float = 0.01, filename: str = "latest.jpg"
) -> Iterator[bytes]:
    """Yield each newly-published annotated JPG as a multipart MJPEG frame."""
    path = directory / filename
    last_modified = -1
    while True:
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
