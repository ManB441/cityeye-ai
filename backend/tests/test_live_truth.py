"""One clock/source contract for metrics, AI images and analytics samples."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.database import TrafficObservationRepository
from app.live_camera import read_live_snapshot, mjpeg_frames
from app.main import create_app
from app.operational_analytics import collect_live_observation
from app.schemas import LiveMetricsResponse


def write_observation(directory, now=1000, **changes):
    directory.mkdir(parents=True, exist_ok=True)
    health = {"camera_id": "camera-3", "state": "ONLINE", "generation": 2,
              "last_frame_at": now, "heartbeat_at": now, "last_connected_at": now - 20}
    metric = LiveMetricsResponse(timestamp=now-1, generation=2, frame=5,
                                active_vehicle_count=7, cars=7, current_detection_count=7,
                                traffic_state="MODERATE").model_dump(mode="json")
    health.update(changes.pop("health", {})); metric.update(changes)
    (directory / "camera_status.json").write_text(json.dumps(health))
    (directory / "live_metrics.json").write_text(json.dumps(metric))
    return health, metric


def test_fresh_live_and_zero_are_real_observations(tmp_path):
    write_observation(tmp_path)
    snapshot = read_live_snapshot(tmp_path, "camera-3", clock=lambda:1000)
    assert snapshot.reason == "FRESH" and snapshot.metrics.cars == 7
    assert snapshot.metrics.traffic_state == "MODERATE" and snapshot.valid_for_seconds == 4
    write_observation(tmp_path, active_vehicle_count=0, cars=0, current_detection_count=0)
    assert read_live_snapshot(tmp_path, "camera-3", clock=lambda:1000).metrics.active_vehicle_count == 0


@pytest.mark.parametrize("change,reason", [
    ({"timestamp":995}, "STALE"), ({"timestamp":0}, "INVALID"),
    ({"timestamp":1001}, "INVALID"), ({"timestamp":float('nan')}, "INVALID"),
    ({"generation":1}, "GENERATION_MISMATCH"),
    ({"health":{"last_connected_at":999.5}}, "GENERATION_MISMATCH"),
    ({"camera_id":"wrong-camera"}, "SOURCE_MISMATCH"),
    ({"health":{"camera_id":"wrong-camera"}}, "SOURCE_MISMATCH"),
    ({"health":{"state":"RECONNECTING"}}, "OFFLINE"),
    ({"health":{"state":"OFFLINE"}}, "OFFLINE"),
    ({"health":{"heartbeat_at":980, "last_frame_at":980}}, "OFFLINE"),
])
def test_invalid_observations_never_expose_stale_counts(tmp_path, change, reason):
    write_observation(tmp_path, **change)
    snapshot = read_live_snapshot(tmp_path, "camera-3", clock=lambda:1000)
    assert snapshot.reason == reason
    assert snapshot.metrics is None and snapshot.valid_for_seconds == 0


def test_missing_and_incomplete_are_not_synthetic_zero(tmp_path):
    write_observation(tmp_path)
    path = tmp_path / "live_metrics.json"; path.unlink()
    assert read_live_snapshot(tmp_path,"camera-3",clock=lambda:1000).reason == "MISSING"
    path.write_text('{"timestamp":999,"generation":2}')
    snapshot = read_live_snapshot(tmp_path,"camera-3",clock=lambda:1000)
    assert snapshot.reason == "INVALID" and snapshot.metrics is None


def test_configured_age_threshold_is_bounded(tmp_path, monkeypatch):
    write_observation(tmp_path)
    monkeypatch.setenv("CITYEYE_LIVE_AI_MAX_AGE_SECONDS","1")
    assert read_live_snapshot(tmp_path,"camera-3",clock=lambda:1000).reason == "STALE"
    monkeypatch.setenv("CITYEYE_LIVE_AI_MAX_AGE_SECONDS","1000")
    with pytest.raises(ValueError): read_live_snapshot(tmp_path,"camera-3",clock=lambda:1000)


@pytest.mark.parametrize("change", [{"timestamp":-20}, {"generation":1}, {"camera_id":"wrong-camera"}, {"health":{"state":"RECONNECTING"}}])
def test_analytics_rejects_untrusted_metrics_even_with_live_heartbeat(tmp_path, change):
    now=time.time()
    if "timestamp" in change: change={"timestamp":now-20}
    directory=tmp_path/"camera-3"; write_observation(directory,now,**change)
    repo=TrafficObservationRepository(tmp_path/"test.db");repo.initialize()
    assert not collect_live_observation(camera_id="camera-3",directory=directory,repository=repo)
    assert repo.list_range("camera-3",0,now+10)==[]


def test_stale_ai_blocks_annotated_stream_but_not_raw_preview(tmp_path, monkeypatch):
    directory=tmp_path/"camera-3";write_observation(directory,time.time(),timestamp=time.time()-20)
    monkeypatch.setattr("app.main.mjpeg_frames",lambda *args,**kwargs:iter([b"controlled-jpeg"]))
    client=TestClient(create_app(live_output_dir=tmp_path))
    assert client.get('/media/live-cameras/camera-3/preview.mjpg').status_code==200
    assert client.get('/media/live-cameras/camera-3.mjpg').status_code==503
    payload=client.get('/api/live-cameras/camera-3/metrics').json()
    assert payload['reason']=='STALE' and payload['metrics'] is None


def test_existing_ai_stream_stops_when_freshness_expires(tmp_path):
    (tmp_path/'latest.jpg').write_bytes(b'\xff\xd8test\xff\xd9')
    assert list(mjpeg_frames(tmp_path,is_current=lambda:False))==[]
