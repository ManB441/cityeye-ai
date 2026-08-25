from pathlib import Path
import sqlite3
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import DuplicateEventError, EventRepository
from app.schemas import EventStatus, TrafficEventIngest


def make_event(event_id: str = "event-1", timestamp: float = 10.0) -> TrafficEventIngest:
    return TrafficEventIngest.model_validate(
        {
            "event_id": event_id,
            "event_type": "WRONG_WAY",
            "timestamp": timestamp,
            "confidence": 0.91,
            "severity": "HIGH",
            "explanation": "Track moved opposite to the allowed direction.",
            "camera_name": "Demo Camera 1",
            "latitude": 31.95,
            "longitude": 35.91,
            "evidence_image": f"evidence/{event_id}.jpg",
            "status": "PROPOSED",
        }
    )


@pytest.fixture
def repository(tmp_path: Path) -> EventRepository:
    repo = EventRepository(tmp_path / "cityeye_test.db")
    repo.initialize()
    return repo


def test_initialize_creates_events_table(repository: EventRepository) -> None:
    with sqlite3.connect(repository.database_path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'events'"
        ).fetchone()

    assert table == ("events",)


def test_initialize_is_idempotent(repository: EventRepository) -> None:
    repository.initialize()
    repository.initialize()

    assert repository.list() == []


def test_add_and_get_event(repository: EventRepository) -> None:
    stored = repository.add(make_event())

    assert stored.event_id == "event-1"
    assert stored.status is EventStatus.PROPOSED
    assert repository.get("event-1") == stored


def test_duplicate_event_id_is_rejected(repository: EventRepository) -> None:
    repository.add(make_event())

    with pytest.raises(DuplicateEventError, match="Event already exists"):
        repository.add(make_event())

    assert len(repository.list()) == 1


def test_get_missing_event_returns_none(repository: EventRepository) -> None:
    assert repository.get("missing") is None


def test_list_returns_newest_video_event_first(repository: EventRepository) -> None:
    repository.add(make_event("older", timestamp=5.0))
    repository.add(make_event("newer", timestamp=12.0))

    events = repository.list()

    assert [event.event_id for event in events] == ["newer", "older"]


@pytest.mark.parametrize("status", [EventStatus.VERIFIED, EventStatus.DISMISSED])
def test_update_status_applies_human_decision(
    repository: EventRepository,
    status: EventStatus,
) -> None:
    repository.add(make_event())

    updated = repository.update_status("event-1", status)

    assert updated is not None
    assert updated.status is status
    assert repository.get("event-1").status is status


def test_update_status_returns_none_for_missing_event(
    repository: EventRepository,
) -> None:
    assert repository.update_status("missing", EventStatus.VERIFIED) is None


def test_update_status_rejects_proposed(repository: EventRepository) -> None:
    repository.add(make_event())

    with pytest.raises(ValueError, match="VERIFIED or DISMISSED"):
        repository.update_status("event-1", EventStatus.PROPOSED)

    assert repository.get("event-1").status is EventStatus.PROPOSED
