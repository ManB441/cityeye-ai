import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.live_camera import mjpeg_frames, read_camera_health, read_live_metrics
from app.main import create_app


def test_missing_live_output_reports_offline(tmp_path: Path) -> None:
    health = read_camera_health(tmp_path)

    assert health.state == "OFFLINE"
    assert health.source_type == "RTSP"


def test_live_status_and_metrics_are_loaded_without_stream_url(tmp_path: Path) -> None:
    (tmp_path / "camera_status.json").write_text(
        json.dumps(
            {
                "camera_id": "pilot-01",
                "source_type": "RTSP",
                "state": "ONLINE",
                "last_frame_at": time.time(),
                "last_error": None,
                "reconnect_attempts": 2,
                "generation": 3,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "live_metrics.json").write_text(
        json.dumps(
            {
                "timestamp": 1_700_000_000.0,
                "frame": 42,
                "generation": 3,
                "current_detection_count": 9,
                "active_vehicle_count": 7,
                "active_track_count": 6,
                "cars": 5,
                "buses": 1,
                "trucks": 0,
                "motorcycles": 1,
                "people": 2,
                "bicycles": 0,
                "traffic_state": "MODERATE",
                "moving_vehicles": 4,
                "stationary_vehicles": 1,
                "unknown_movement_vehicles": 1,
            }
        ),
        encoding="utf-8",
    )

    health = read_camera_health(tmp_path)
    metrics = read_live_metrics(tmp_path)

    assert health.state == "ONLINE"
    assert health.generation == 3
    assert "url" not in health.model_dump()
    assert "rtsp_url" not in health.model_dump()
    assert metrics.frame == 42
    assert metrics.active_vehicle_count == 7
    assert metrics.active_track_count == 6


def test_camera_3_metrics_endpoint_accepts_current_worker_schema(tmp_path: Path) -> None:
    directory = tmp_path / "camera-3"
    directory.mkdir()
    payload = {
        "frame": 94,
        "timestamp": 1_700_000_001.0,
        "generation": 2,
        "current_detection_count": 2,
        "active_vehicle_count": 1,
        "active_track_count": 0,
        "cars": 1,
        "buses": 0,
        "trucks": 0,
        "motorcycles": 0,
        "people": 1,
        "bicycles": 0,
        "traffic_state": "NORMAL",
        "moving_vehicles": 0,
        "stationary_vehicles": 0,
        "unknown_movement_vehicles": 0,
    }
    (directory / "live_metrics.json").write_text(json.dumps(payload), encoding="utf-8")
    client = TestClient(create_app(live_output_dir=tmp_path))

    response = client.get("/api/live-cameras/camera-3/metrics")

    assert response.status_code == 200
    assert response.json() == payload


def test_mjpeg_generator_wraps_latest_jpeg(tmp_path: Path) -> None:
    jpeg = b"\xff\xd8fake-jpeg\xff\xd9"
    (tmp_path / "latest.jpg").write_bytes(jpeg)

    payload = next(mjpeg_frames(tmp_path, poll_seconds=0.001))

    assert payload.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n")
    assert jpeg in payload


def test_mjpeg_generator_can_stream_raw_preview(tmp_path: Path) -> None:
    jpeg = b"\xff\xd8raw-preview\xff\xd9"
    (tmp_path / "preview.jpg").write_bytes(jpeg)
    payload = next(mjpeg_frames(tmp_path, poll_seconds=0.001, filename="preview.jpg"))
    assert jpeg in payload


def test_stale_online_camera_is_reported_reconnecting(tmp_path: Path) -> None:
    (tmp_path / "camera_status.json").write_text(
        json.dumps({
            "camera_id": "pilot-01",
            "source_type": "RTSP",
            "state": "ONLINE",
            "last_frame_at": 90.0,
            "processing_fps": 3.8,
        }),
        encoding="utf-8",
    )

    health = read_camera_health(
        tmp_path, clock=lambda: 101.0, stale_after_seconds=10.0
    )

    assert health.state == "OFFLINE"
    assert health.processing_fps == 0.0
    assert "stale" in (health.last_error or "").lower()


def test_online_without_any_frame_timestamp_is_not_reported_healthy(
    tmp_path: Path,
) -> None:
    (tmp_path / "camera_status.json").write_text(
        json.dumps({
            "camera_id": "pilot-01",
            "source_type": "RTSP",
            "state": "ONLINE",
            "last_frame_at": None,
            "processing_fps": 4.0,
        }),
        encoding="utf-8",
    )

    health = read_camera_health(tmp_path, clock=lambda: 100.0)

    assert health.state == "OFFLINE"
    assert health.processing_fps == 0.0


def test_live_camera_api_exposes_status_metrics_and_events(tmp_path: Path) -> None:
    (tmp_path / "camera_status.json").write_text(
        json.dumps(
            {
                "camera_id": "pilot-01",
                "source_type": "RTSP",
                "state": "RECONNECTING",
                "last_frame_at": None,
                "last_error": "stream unavailable",
                "reconnect_attempts": 1,
                "generation": 0,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "live_metrics.json").write_text(
        json.dumps(
            {
                "timestamp": 1_700_000_000.0,
                "frame": 0,
                "active_vehicle_count": 0,
                "cars": 0,
                "buses": 0,
                "trucks": 0,
                "motorcycles": 0,
                "people": 0,
                "bicycles": 0,
                "traffic_state": "UNKNOWN",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "events.json").write_text("[]", encoding="utf-8")

    client = TestClient(create_app(live_output_dir=tmp_path))

    status_response = client.get("/api/live-camera/status")
    metrics_response = client.get("/api/live-camera/metrics")
    events_response = client.get("/api/live-camera/events")

    assert status_response.status_code == 200
    assert status_response.json()["state"] == "OFFLINE"
    assert metrics_response.status_code == 200
    assert metrics_response.json()["traffic_state"] == "UNKNOWN"
    assert events_response.status_code == 200
    assert events_response.json() == {"events": [], "total": 0}


def test_multi_camera_api_keeps_outputs_isolated(tmp_path: Path) -> None:
    for camera_id, cars in (("camera-3", 3), ("camera-5", 5), ("camera-7", 7)):
        directory = tmp_path / camera_id
        directory.mkdir()
        (directory / "camera_status.json").write_text(
            json.dumps({
                "camera_id": camera_id,
                "source_type": "RTSP",
                "state": "ONLINE",
                "last_frame_at": time.time(),
                "processing_fps": 2.0,
            }),
            encoding="utf-8",
        )
        (directory / "live_metrics.json").write_text(
            json.dumps({"frame": 1, "cars": cars, "traffic_state": "NORMAL"}),
            encoding="utf-8",
        )
        (directory / "events.json").write_text("[]", encoding="utf-8")

    client = TestClient(create_app(live_output_dir=tmp_path))

    cameras = client.get("/api/live-cameras")
    assert cameras.status_code == 200
    assert [item["camera_id"] for item in cameras.json()] == [
        "camera-3", "camera-5", "camera-7",
    ]
    assert client.get("/api/live-cameras/camera-5/metrics").json()["cars"] == 5
    assert client.get("/api/live-cameras/camera-7/events").json() == {
        "events": [], "total": 0,
    }


def test_live_camera_listing_respects_configured_pilot_allowlist(
    tmp_path: Path, monkeypatch,
) -> None:
    for camera_id in ("camera-3", "camera-5", "camera-7"):
        directory = tmp_path / camera_id
        directory.mkdir()
        (directory / "camera_status.json").write_text(
            json.dumps({
                "camera_id": camera_id,
                "source_type": "RTSP",
                "state": "ONLINE",
                "last_frame_at": time.time(),
            }),
            encoding="utf-8",
        )

    monkeypatch.setenv("CITYEYE_LIVE_CAMERA_IDS", "camera-3")
    client = TestClient(create_app(live_output_dir=tmp_path))

    response = client.get("/api/live-cameras")

    assert response.status_code == 200
    assert [item["camera_id"] for item in response.json()] == ["camera-3"]


def test_multi_camera_api_rejects_path_traversal(tmp_path: Path) -> None:
    client = TestClient(create_app(live_output_dir=tmp_path))

    response = client.get("/api/live-cameras/%2E%2E%2Fsecret/status")

    assert response.status_code in {400, 404}


def test_live_preview_rejects_offline_camera_even_when_old_frame_exists(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "camera-3"
    directory.mkdir()
    (directory / "camera_status.json").write_text(
        json.dumps({
            "camera_id": "camera-3",
            "source_type": "RTSP",
            "state": "ONLINE",
            "last_frame_at": time.time() - 60,
        }),
        encoding="utf-8",
    )
    (directory / "preview.jpg").write_bytes(b"\xff\xd8old-frame\xff\xd9")

    client = TestClient(create_app(live_output_dir=tmp_path))
    response = client.get("/media/live-cameras/camera-3/preview.mjpg")

    assert response.status_code == 503
    assert response.json() == {"detail": "Camera camera-3 is offline."}

    annotated_response = client.get("/media/live-cameras/camera-3.mjpg")
    assert annotated_response.status_code == 503
    assert annotated_response.json() == {"detail": "Camera camera-3 is offline."}
