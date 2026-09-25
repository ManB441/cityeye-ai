import json
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.database import CitizenReportRepository, EventRepository
from app.main import create_app
from app.map_view import MapConfig, map_snapshot
from app.schemas import TrafficEventIngest, CitizenReportCreate, LiveMetricsSnapshot, LiveMetricsResponse, CameraHealthResponse, EventStatus
from test_auth_api import configure_required_auth, login, ADMIN_PASSWORD


def config(public=False):
    return MapConfig.model_validate({"cameras": [{"camera_id": "camera-3", "label": "Synthetic test area",
        "position": {"lat": 31, "lng": 35}, "location_confirmed": True, "public": public,
        "road": [{"lat": 31, "lng": 35}, {"lat": 31.001, "lng": 35.001}], "traffic_calibrated": True}]})


def repositories(tmp_path):
    events = EventRepository(tmp_path / "map.db"); events.initialize()
    reports = CitizenReportRepository(tmp_path / "map.db"); reports.initialize()
    return events, reports


def test_no_guessed_coordinates_or_unconfigured_locations(tmp_path):
    events, reports = repositories(tmp_path)
    result = map_snapshot(MapConfig(), tmp_path, events, [])
    assert result["features"] == []
    c = config(); c.cameras[0].location_confirmed = False
    assert map_snapshot(c, tmp_path, events, [])["features"] == []


def test_offline_road_unknown_not_zero_or_green(tmp_path):
    events, reports = repositories(tmp_path)
    result = map_snapshot(config(), tmp_path, events, [])
    road = next(f for f in result["features"] if f["properties"]["kind"] == "road")
    camera = next(f for f in result["features"] if f["properties"]["kind"] == "camera")
    assert road["properties"]["status"] == "UNKNOWN"
    assert camera["properties"]["vehicles"] is None


def test_public_hides_cameras_private_locations_and_proposals(tmp_path):
    events, reports = repositories(tmp_path)
    for status in ("PROPOSED", "VERIFIED", "DISMISSED"):
        events.add(TrafficEventIngest(event_id=status, event_type="STOPPED_VEHICLE", timestamp=time.time(),
            confidence=.9, severity="HIGH", explanation="Synthetic", camera_name="Other display name",
            latitude=0, longitude=0, evidence_image="private.jpg", source_type="LIVE_CAMERA", source_id="camera-3",
            status="PROPOSED"))
        if status != "PROPOSED":
            events.update_status(status, EventStatus(status))
    assert map_snapshot(config(), tmp_path, events, [], citizen=True)["features"] == []
    public = map_snapshot(config(True), tmp_path, events, [], citizen=True)
    assert {f["properties"]["kind"] for f in public["features"]} == {"road", "incident"}
    incident = next(f for f in public["features"] if f["properties"]["kind"] == "incident")
    assert incident["properties"]["status"] == "VERIFIED"
    assert incident["geometry"]["coordinates"] == [35, 31]
    assert incident["properties"]["location_accuracy"] == "CAMERA_AREA_APPROXIMATE"
    assert "private.jpg" not in json.dumps(public)


def test_fresh_traffic_requires_confirmed_traffic_calibration(tmp_path, monkeypatch):
    events, _ = repositories(tmp_path)
    snapshot = LiveMetricsSnapshot(camera_id="camera-3", checked_at=time.time(), max_age_seconds=5,
        valid_for_seconds=3, reason="FRESH", health=CameraHealthResponse(camera_id="camera-3"),
        metrics=LiveMetricsResponse(timestamp=time.time(), traffic_state="HEAVY_CONGESTION"))
    monkeypatch.setattr("app.map_view.read_live_snapshot", lambda *args: snapshot)
    c = config()
    result = map_snapshot(c, tmp_path, events, [])
    assert result["features"][1]["properties"]["status"] == "HEAVY_CONGESTION"
    c.cameras[0].traffic_calibrated = False
    assert map_snapshot(c, tmp_path, events, [])["features"][1]["properties"]["status"] == "UNKNOWN"


def test_report_projection_does_not_expose_voter_identity(tmp_path):
    events, reports = repositories(tmp_path)
    report = reports.add(CitizenReportCreate(category="CONGESTION", description="User observation",
        latitude=31, longitude=35, demo_user_id="private-user-id"))
    result = map_snapshot(MapConfig(), tmp_path, events, [report], citizen=True)
    assert result["features"][0]["properties"]["status"] == "PENDING"
    assert "private-user-id" not in json.dumps(result)


def test_map_api_auth_and_invalid_config(tmp_path, monkeypatch):
    configure_required_auth(monkeypatch, tmp_path)
    with TestClient(create_app(database_path=tmp_path / "api.db")) as client:
        assert client.get("/api/map").status_code == 401
        login(client, "admin", ADMIN_PASSWORD)
        assert client.get("/api/map").json()["scope"] == "OPERATIONS"
        client.post("/api/users", json={"username": "citizen", "password": ADMIN_PASSWORD, "role": "CITIZEN"})
        login(client, "citizen", ADMIN_PASSWORD)
        assert client.get("/api/map").json()["scope"] == "PUBLIC"
        assert client.get("/api/events").status_code == 403
        monkeypatch.setenv("CITYEYE_MAP_CONFIG", str(tmp_path / "absent.json"))
        assert client.get("/api/map").status_code == 503


def test_invalid_geography_rejected():
    c = config().model_dump(); c["cameras"][0]["position"]["lat"] = 100
    with pytest.raises(ValidationError): MapConfig.model_validate(c)
    c = config().model_dump(); c["cameras"].append(c["cameras"][0])
    with pytest.raises(ValidationError): MapConfig.model_validate(c)
