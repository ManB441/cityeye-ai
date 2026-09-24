"""Controlled proposal delivery, restart, evidence, review and authorization tests."""
import json
from pathlib import Path
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthRepository, AuthenticatedUser
from app.database import EventRepository
from app.live_incidents import LiveIncidentImporter
from app.main import create_app
from app.schemas import EventStatus, TrafficEventIngest
from test_auth_api import configure_required_auth, login, ADMIN_PASSWORD
from test_events_api import event_payload


def delivery(root: Path, event_id: str = "controlled-live"):
    directory = root / "camera-3"
    evidence = directory / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    event = event_payload(event_id, 1_789_670_000.25)
    event.update(camera_name="DVR Camera 3", details={"source_type": "RTSP", "camera_id": "camera-3", "timestamp_kind": "WALL_CLOCK_UNIX", "track_id": 7, "direction_score": 0.91})
    (evidence / f"{event_id}.jpg").write_bytes(b"\xff\xd8controlled-evidence\xff\xd9")
    (directory / "events.json").write_text(json.dumps([event]))
    return event


def wait_for_incident(repository, event_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        incident = repository.get(event_id)
        if incident is not None:
            return incident
        time.sleep(0.05)
    pytest.fail("Background ingestion did not persist the incident")


@pytest.mark.parametrize("role,decision,expected", [
    ("EMPLOYEE", "verify", "VERIFIED"), ("EMPLOYEE", "dismiss", "DISMISSED"),
    ("ADMIN", "verify", "VERIFIED"), ("ADMIN", "dismiss", "DISMISSED"),
])
def test_automatic_delivery_review_and_restart(monkeypatch, tmp_path, role, decision, expected):
    configure_required_auth(monkeypatch, tmp_path)
    db = tmp_path / "test.db"
    root = tmp_path / "live"
    def app():
        return create_app(database_path=db, live_output_dir=root)
    with TestClient(app()) as client:
        # Created AFTER startup. No product GET or review is needed to ingest.
        event = delivery(root)
        repository = EventRepository(db)
        stored = wait_for_incident(repository, event["event_id"])
        assert stored.timestamp == event["timestamp"]
        assert stored.details == event["details"]
        assert stored.evidence_image == event["evidence_image"]
        assert stored.source_type == "LIVE_CAMERA" and stored.source_id == "camera-3"
        assert stored.status == EventStatus.PROPOSED
        users = AuthRepository(db)
        users.create_user("operator", "operator-password-123", "CITIZEN")
        login(client, "operator", "operator-password-123")
        endpoint = f'/api/events/{event["event_id"]}'
        assert client.get("/api/events").status_code == 403
        evidence_url = f'/evidence/live-cameras/camera-3/{event["event_id"]}.jpg'
        assert client.get(evidence_url).status_code == 403
        for action in ("verify", "dismiss"):
            assert client.post(f"{endpoint}/{action}").status_code == 403
            assert client.post(f'/api/live-cameras/camera-3/events/{event["event_id"]}/{action}').status_code == 403
        if role == "EMPLOYEE":
            users.create_user("reviewer", "reviewer-password-123", role)
            login(client, "reviewer", "reviewer-password-123")
        else:
            login(client, "admin", ADMIN_PASSWORD)
        assert client.post(f"{endpoint}/{decision}").json()["status"] == expected
        assert client.get(endpoint).json()["status"] == expected
        assert client.get("/api/live-cameras/camera-3/events").json()["events"][0]["status"] == expected
        # Repeat delivery with a new importer (producer/backend restart replay).
        LiveIncidentImporter(root, repository).sync("camera-3")
        assert len(repository.list()) == 1
    with TestClient(app()) as client:
        login(client, "admin", ADMIN_PASSWORD)
        assert client.get("/api/events").json()["total"] == 1
        assert client.get(endpoint).json()["status"] == expected
        assert client.get(evidence_url).status_code == 200
        audit = client.get("/api/audit").json()["entries"]
        decisions = [entry for entry in audit if entry["target_id"] == event["event_id"]]
        assert len(decisions) == 1
        assert decisions[0]["previous_value"] == "PROPOSED"
        assert decisions[0]["new_value"] == expected
        assert decisions[0]["actor_username"] == ("admin" if role == "ADMIN" else "reviewer")
        # DB history and review no longer require the producer's JSON file.
        (root / "camera-3" / "events.json").unlink()
        assert client.get("/api/live-cameras/camera-3/events").json()["total"] == 1
        assert client.get(evidence_url).status_code == 200


def test_retries_missing_evidence_and_bad_json_without_losing_other_events(tmp_path):
    db = tmp_path / "test.db"
    repo = EventRepository(db); repo.initialize()
    root = tmp_path / "live"
    event = delivery(root)
    directory = root / "camera-3"
    evidence = directory / event["evidence_image"]
    data = evidence.read_bytes(); evidence.unlink()
    importer = LiveIncidentImporter(root, repo)
    importer.sync("camera-3")
    assert repo.list() == []
    evidence.write_bytes(data)
    importer.sync("camera-3")  # same events.json fingerprint must still retry
    assert len(repo.list()) == 1
    (directory / "events.json").write_text("[")
    importer.sync_safely("camera-3")
    assert len(repo.list()) == 1
    next_event = dict(event, event_id="next-event")
    (directory / "events.json").write_text(json.dumps([{"invalid": True}, next_event]))
    importer.sync("camera-3")
    assert len(repo.list()) == 2


def test_duplicate_delivery_does_not_write_or_reset_review(tmp_path):
    repo = EventRepository(tmp_path / "test.db"); repo.initialize()
    root = tmp_path / "live"; event = delivery(root)
    importer = LiveIncidentImporter(root, repo); importer.sync("camera-3")
    repo.update_status(event["event_id"], EventStatus.VERIFIED)
    importer.sync("camera-3")
    LiveIncidentImporter(root, repo).sync("camera-3")
    assert len(repo.list()) == 1
    assert repo.get(event["event_id"]).status == EventStatus.VERIFIED


def test_symlink_evidence_cannot_escape_source(tmp_path):
    repo = EventRepository(tmp_path / "test.db"); repo.initialize()
    root = tmp_path / "live"; event = delivery(root)
    evidence = root / "camera-3" / event["evidence_image"]
    outside = tmp_path / "outside.jpg"; outside.write_bytes(evidence.read_bytes())
    evidence.unlink(); evidence.symlink_to(outside)
    LiveIncidentImporter(root, repo).sync("camera-3")
    assert repo.list() == []


def test_review_rolls_back_if_audit_write_fails(tmp_path):
    db = tmp_path / "test.db"; repo = EventRepository(db); repo.initialize()
    AuthRepository(db).initialize()
    repo.add(TrafficEventIngest.model_validate(event_payload()))
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_log BEGIN SELECT RAISE(ABORT, 'controlled audit failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        repo.review_with_audit("event-1", EventStatus.VERIFIED, AuthenticatedUser("r", "reviewer", "EMPLOYEE"), "test-request")
    assert repo.get("event-1").status == EventStatus.PROPOSED
    assert AuthRepository(db).list_audit() == []


def test_concurrent_replay_inserts_only_one_incident(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    repo = EventRepository(tmp_path / "test.db"); repo.initialize()
    root = tmp_path / "live"; delivery(root)
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(lambda _: LiveIncidentImporter(root, repo).sync("camera-3"), range(8)))
    assert len(repo.list()) == 1


def test_existing_review_is_adopted_without_losing_metadata(tmp_path):
    repo = EventRepository(tmp_path / "test.db"); repo.initialize()
    root = tmp_path / "live"; event = delivery(root)
    repo.add(TrafficEventIngest.model_validate(event))
    repo.update_status(event["event_id"], EventStatus.DISMISSED)
    LiveIncidentImporter(root, repo).sync("camera-3")
    stored = repo.get(event["event_id"])
    assert stored.status == EventStatus.DISMISSED and stored.source_id == "camera-3"
    assert stored.details == event["details"]


def test_event_source_cannot_be_reassigned(tmp_path):
    repo = EventRepository(tmp_path / "test.db"); repo.initialize()
    event = TrafficEventIngest.model_validate({**event_payload(), "source_type": "LIVE_CAMERA", "source_id": "camera-3"})
    repo.ingest_once(event)
    with pytest.raises(ValueError, match="different source"):
        repo.ingest_once(event.model_copy(update={"source_id": "another-camera"}))
    assert repo.get(event.event_id).source_id == "camera-3"
