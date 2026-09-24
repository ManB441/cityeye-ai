import json
from pathlib import Path
import sys
import time

from fastapi.testclient import TestClient
import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import EventRepository, TrafficObservationRepository
from app.main import create_app
from app.operational_analytics import (
    build_operational_analytics,
    collect_live_observation,
    query_operational_analytics,
)
from app.schemas import TrafficEventIngest, TrafficObservation


def observation(
    timestamp: float,
    *,
    camera_id: str = "camera-3",
    vehicles: int = 2,
    cars: int = 2,
    traffic_status: str = "NORMAL",
) -> TrafficObservation:
    return TrafficObservation(
        camera_id=camera_id,
        interval_start=(timestamp // 60) * 60,
        observed_at=timestamp,
        generation=1,
        vehicles=vehicles,
        cars=cars,
        buses=0,
        trucks=0,
        motorcycles=0,
        bicycles=0,
        people=0,
        moving_vehicles=vehicles,
        stationary_vehicles=0,
        traffic_status=traffic_status,
        capture_fps=11.5,
        ai_fps=3.8,
    )


def repositories(tmp_path: Path):
    database = tmp_path / "cityeye.db"
    observations = TrafficObservationRepository(database)
    events = EventRepository(database)
    observations.initialize()
    events.initialize()
    return observations, events


def test_live_collection_persists_once_per_interval(tmp_path: Path) -> None:
    repository, _ = repositories(tmp_path)
    directory = tmp_path / "camera-3"
    directory.mkdir()
    now = time.time()
    (directory / "camera_status.json").write_text(json.dumps({
        "camera_id": "camera-3", "source_type": "RTSP", "state": "ONLINE",
        "last_frame_at": now, "heartbeat_at": now,
        "generation": 4, "camera_capture_fps": 11.8, "ai_inference_fps": 3.9,
    }))
    (directory / "live_metrics.json").write_text(json.dumps({
        "frame": 50, "timestamp": now, "generation": 4, "current_detection_count": 4,
        "active_vehicle_count": 3, "active_track_count": 2,
        "cars": 2, "buses": 0, "trucks": 1, "motorcycles": 0,
        "bicycles": 0, "people": 1, "moving_vehicles": 2,
        "stationary_vehicles": 1, "unknown_movement_vehicles": 0,
        "traffic_state": "NORMAL",
    }))

    assert collect_live_observation(
        camera_id="camera-3", directory=directory, repository=repository,
    ) is True
    assert collect_live_observation(
        camera_id="camera-3", directory=directory, repository=repository,
    ) is False
    stored = repository.list_range("camera-3", now - 1, now + 1)
    assert len(stored) == 1
    assert stored[0].observed_at == now
    assert stored[0].vehicles == 3
    assert stored[0].capture_fps == 11.8

    reopened = TrafficObservationRepository(tmp_path / "cityeye.db")
    reopened.initialize()
    persisted = reopened.list_range("camera-3", now - 1, now + 1)
    assert len(persisted) == 1
    assert persisted[0] == stored[0]


def test_collection_skips_generation_mismatch_without_crashing(tmp_path: Path) -> None:
    repository, _ = repositories(tmp_path)
    directory = tmp_path / "camera-3"
    directory.mkdir()
    (directory / "camera_status.json").write_text(json.dumps({
        "camera_id": "camera-3", "state": "ONLINE", "last_frame_at": 100,
        "heartbeat_at": 100, "generation": 2,
    }))
    (directory / "live_metrics.json").write_text(json.dumps({
        "timestamp": 100, "generation": 1,
    }))
    assert collect_live_observation(
        camera_id="camera-3", directory=directory, repository=repository,
    ) is False
    assert repository.list_range("camera-3", 0, 200) == []


def test_collection_does_not_fabricate_data_when_camera_files_are_absent(
    tmp_path: Path,
) -> None:
    repository, _ = repositories(tmp_path)
    directory = tmp_path / "camera-3"
    directory.mkdir()
    assert collect_live_observation(
        camera_id="camera-3", directory=directory, repository=repository,
    ) is False
    assert repository.list_range("camera-3", 0, time.time()) == []


@pytest.mark.parametrize("hours", [24, 24 * 7, 24 * 30])
def test_range_filtering_for_supported_periods(tmp_path: Path, hours: int) -> None:
    repository, _ = repositories(tmp_path)
    end = 2_000_000_000.0
    inside = end - hours * 3600 + 1
    outside = end - hours * 3600 - 1
    repository.add(observation(inside))
    repository.add(observation(outside))
    rows = repository.list_range("camera-3", end - hours * 3600, end)
    assert [row.observed_at for row in rows] == [inside]


def test_today_filtering_uses_requested_start(tmp_path: Path) -> None:
    repository, _ = repositories(tmp_path)
    start = 1_800_000_000.0
    repository.add(observation(start - 1))
    repository.add(observation(start + 1))
    assert len(repository.list_range("camera-3", start, start + 86_400)) == 1


def test_camera_filtering_isolated(tmp_path: Path) -> None:
    repository, _ = repositories(tmp_path)
    repository.add(observation(1_700_000_001, camera_id="camera-3"))
    repository.add(observation(1_700_000_002, camera_id="camera-5"))
    assert len(repository.list_range("camera-3", 0, 2_000_000_000)) == 1


def test_bucketing_peak_congestion_and_composition_are_real() -> None:
    base = 1_699_999_800.0  # aligned five-minute boundary
    rows = [
        observation(base + 10, vehicles=2, cars=2),
        observation(base + 70, vehicles=4, cars=3, traffic_status="MODERATE"),
        observation(base + 130, vehicles=6, cars=5, traffic_status="HEAVY_CONGESTION"),
        observation(base + 400, vehicles=1, cars=1),
    ]
    result = build_operational_analytics(
        camera_id="camera-3", start=base, end=base + 3_600,
        observations=rows, data_since=rows[0].observed_at, events=[],
    )
    assert len(result.traffic_series) == 2
    assert result.peak_vehicle_count == 4.0
    assert result.congestion_episodes == 1
    assert result.congestion_duration_minutes == 1.0
    assert result.vehicle_composition_observations["cars"] == 11
    assert result.average_vehicles_observed == 3.25


def test_incident_counts_use_persisted_matching_camera_events(tmp_path: Path) -> None:
    observations, events = repositories(tmp_path)
    observations.add(observation(1_700_000_010))
    events.add(TrafficEventIngest(
        event_id="real-live-event", event_type="WRONG_WAY",
        source_type="LIVE_CAMERA", source_id="camera-3",
        timestamp=1_700_000_020, confidence=0.9, severity="HIGH",
        explanation="Real tracked movement", camera_name="DVR Camera 3",
        latitude=31.9, longitude=35.2, evidence_image="real.jpg",
    ))
    result = query_operational_analytics(
        camera_id="camera-3", start=1_700_000_000, end=1_700_000_100,
        observations=observations, events=events,
    )
    assert result.incident_count == 1
    assert result.incidents_by_type == {"WRONG_WAY": 1}
    assert result.incidents_by_status == {"PROPOSED": 1}


def test_empty_and_partial_period_are_explicit(tmp_path: Path) -> None:
    observations, events = repositories(tmp_path)
    observations.add(observation(1_700_000_100))
    empty = query_operational_analytics(
        camera_id="camera-3", start=1_600_000_000, end=1_600_000_100,
        observations=observations, events=events,
    )
    assert empty.samples == 0
    assert empty.average_vehicles_observed is None
    assert empty.traffic_series == []
    assert empty.data_since == 1_700_000_100


def test_analytics_api_returns_valid_real_schema(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CITYEYE_LIVE_CAMERA_IDS", "camera-3")
    with TestClient(create_app(
        database_path=tmp_path / "cityeye.db",
        live_output_dir=tmp_path / "live",
    )) as client:
        response = client.get(
            "/api/analytics/traffic?camera_id=camera-3&start=100&end=200"
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["camera_id"] == "camera-3"
    assert payload["samples"] == 0
    assert payload["traffic_series"] == []


def test_incident_identity_does_not_merge_display_names(tmp_path):
    observations, events = repositories(tmp_path)
    base = dict(event_type="WRONG_WAY", timestamp=100, confidence=.9,
                severity="HIGH", explanation="Observed motion", camera_name="DVR Camera 3",
                latitude=0, longitude=0, evidence_image="evidence.jpg")
    for event_id, source_type, source_id, name in [
        ("correct", "LIVE_CAMERA", "camera-3", "Renamed camera"),
        ("other-camera", "LIVE_CAMERA", "camera-5", "DVR Camera 3"),
        ("recorded", "RECORDED_SCENARIO", "demo", "DVR Camera 3"),
        ("legacy", None, None, "DVR Camera 3"),
    ]:
        events.add(TrafficEventIngest(**{**base, "event_id": event_id,
                   "source_type": source_type, "source_id": source_id, "camera_name": name}))
    result = query_operational_analytics(camera_id="camera-3", start=0, end=200,
                                        observations=observations, events=events)
    assert result.incident_count == 1
    assert result.incidents_by_type == {"WRONG_WAY": 1}


def test_moderate_and_unknown_are_not_heavy_congestion():
    rows = [observation(10, traffic_status="MODERATE"),
            observation(70, traffic_status="UNKNOWN")]
    result = build_operational_analytics(camera_id="camera-3", start=0, end=200,
                                        observations=rows, data_since=10, events=[])
    assert result.congestion_episodes == 0
    assert result.congestion_duration_minutes == 0
    assert result.traffic_status_samples == {"MODERATE": 1, "UNKNOWN": 1}


def test_congestion_episode_breaks_on_generation_and_missing_samples():
    rows = [observation(10, traffic_status="HEAVY_CONGESTION"),
            observation(70, traffic_status="HEAVY_CONGESTION").model_copy(update={"generation": 2}),
            observation(250, traffic_status="HEAVY_CONGESTION").model_copy(update={"generation": 2})]
    result = build_operational_analytics(camera_id="camera-3", start=0, end=300,
                                        observations=rows, data_since=10, events=[])
    assert result.congestion_episodes == 3
    assert result.congestion_duration_minutes == 3


def test_irregular_observations_keep_real_times_and_zero_without_filling_gaps():
    rows = [observation(10, vehicles=0, cars=0), observation(910, vehicles=8, cars=8)]
    result = build_operational_analytics(camera_id="camera-3", start=0, end=1200,
                                        observations=rows, data_since=10, events=[])
    assert [p.timestamp for p in result.traffic_series] == [0, 900]
    assert [p.average_vehicles_observed for p in result.traffic_series] == [0, 8]
    assert result.samples == 2
    assert result.first_sample_at == 10
    assert result.latest_sample_at == 910
