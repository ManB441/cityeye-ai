import sqlite3
import base64
import json

from fastapi.testclient import TestClient

from app.database import EventRepository
from app.main import create_app
from app.schemas import TrafficEventIngest


def seed(database, count=5005):
    repo = EventRepository(database)
    repo.initialize()
    repo.add(TrafficEventIngest(event_id="seed", event_type="WRONG_WAY", timestamp=100,
        confidence=.9, severity="HIGH", explanation="Synthetic history", camera_name="Same name",
        latitude=0, longitude=0, evidence_image="kept.jpg", source_type="LIVE_CAMERA", source_id="camera-3"))
    with sqlite3.connect(database) as con:
        con.executemany("""INSERT INTO events_v2 (event_id,event_type,timestamp,confidence,severity,explanation,
            camera_name,latitude,longitude,evidence_image,status,source_type,source_id)
            VALUES (?, 'WRONG_WAY', ?, .9, 'HIGH', 'Synthetic history', 'Same name', 0,0,'kept.jpg',
                    'PROPOSED','LIVE_CAMERA','camera-3')""", [(f"event-{i:05}", i // 3) for i in range(count)])
    return repo


def test_bounded_pages_have_no_duplicates_or_missing_ids_during_inserts(tmp_path):
    database = tmp_path / "history.db"
    repo = seed(database)
    expected = [event.event_id for event in repo.list()]
    with TestClient(create_app(database_path=database, live_output_dir=tmp_path / "live")) as client:
        page = client.get("/api/events?source_type=LIVE_CAMERA&limit=100").json()
        assert len(page["events"]) == 100
        seen = [e["event_id"] for e in page["events"]]
        assert page["total"] == len(expected)
        # A backdated new row must not enter the snapshot mid-pagination.
        repo.add(repo.get("seed").model_copy(update={"event_id": "late", "timestamp": 1}))
        while page["next_cursor"]:
            response = client.get("/api/events", params={"source_type": "LIVE_CAMERA", "limit": 100, "cursor": page["next_cursor"]})
            assert response.status_code == 200
            page = response.json()
            assert len(page["events"]) <= 100
            seen.extend(e["event_id"] for e in page["events"])
        assert seen == expected
        assert len(set(seen)) == len(seen)
        assert client.get("/api/events?limit=201").status_code == 422
        assert client.get("/api/events?cursor=garbage").status_code == 400
        # User-supplied cursors must not overflow SQLite integer bindings.
        huge_time = base64.urlsafe_b64encode(json.dumps([1, 10**100, "seed", None, None]).encode()).decode()
        assert client.get("/api/events", params={"cursor": huge_time}).status_code == 200
        assert client.get("/api/events").json()["total"] == len(expected) + 1


def test_cursor_cannot_switch_source_and_does_not_delete_evidence(tmp_path):
    database = tmp_path / "history.db"
    seed(database, 5)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    image = evidence / "kept.jpg"
    image.write_bytes(b"synthetic evidence sentinel")
    with TestClient(create_app(database_path=database, evidence_dir=evidence, live_output_dir=tmp_path / "live")) as client:
        page = client.get("/api/events?source_type=LIVE_CAMERA&source_id=camera-3&limit=2").json()
        response = client.get("/api/events", params={"cursor": page["next_cursor"], "source_id": "camera-5", "source_type": "LIVE_CAMERA"})
        assert response.status_code == 400
        assert client.get("/evidence/kept.jpg").content == image.read_bytes()
    assert image.read_bytes() == b"synthetic evidence sentinel"


def test_analytics_aggregates_without_materializing_event_history(tmp_path, monkeypatch):
    from app.database import TrafficObservationRepository
    from app.operational_analytics import query_operational_analytics
    database = tmp_path / "history.db"
    events = seed(database, 5005)
    observations = TrafficObservationRepository(database)
    observations.initialize()
    def unbounded_read():
        raise AssertionError("Analytics must not load all event objects")
    monkeypatch.setattr(events, "list", unbounded_read)
    result = query_operational_analytics(camera_id="camera-3", start=0, end=10000,
                                        observations=observations, events=events)
    assert result.incident_count == 5006
    assert result.incidents_by_type == {"WRONG_WAY": 5006}
