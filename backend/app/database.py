"""Small SQLite repository for CityEye AI traffic events."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

from app.schemas import EventStatus, TrafficEventIngest, TrafficEventResponse


class DuplicateEventError(ValueError):
    """Raised when an event ID already exists in SQLite."""


class EventRepository:
    """Persist and review traffic events using one local SQLite file."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the events table and indexes if they do not exist."""
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN ('WRONG_WAY', 'STOPPED_VEHICLE', 'CONGESTION')
                    ),
                    timestamp REAL NOT NULL CHECK (timestamp >= 0),
                    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
                    severity TEXT NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH')),
                    explanation TEXT NOT NULL,
                    camera_name TEXT NOT NULL,
                    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
                    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
                    evidence_image TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PROPOSED' CHECK (
                        status IN ('PROPOSED', 'VERIFIED', 'DISMISSED')
                    ),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_events_timestamp
                ON events(timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_events_status
                ON events(status);
                """
            )

    def add(self, event: TrafficEventIngest) -> TrafficEventResponse:
        """Insert one AI-proposed event and reject duplicate IDs."""
        payload = event.model_dump(mode="json")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO events (
                        event_id, event_type, timestamp, confidence, severity,
                        explanation, camera_name, latitude, longitude,
                        evidence_image, status
                    ) VALUES (
                        :event_id, :event_type, :timestamp, :confidence, :severity,
                        :explanation, :camera_name, :latitude, :longitude,
                        :evidence_image, :status
                    )
                    """,
                    payload,
                )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed: events.event_id" in str(exc):
                raise DuplicateEventError(
                    f"Event already exists: {event.event_id}"
                ) from exc
            raise

        stored = self.get(event.event_id)
        if stored is None:
            raise RuntimeError(f"Stored event could not be read: {event.event_id}")
        return stored

    def get(self, event_id: str) -> TrafficEventResponse | None:
        """Return one event by ID or None when it does not exist."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT event_id, event_type, timestamp, confidence, severity,
                       explanation, camera_name, latitude, longitude,
                       evidence_image, status
                FROM events
                WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
        return self._to_event(row) if row is not None else None

    def list(self) -> list[TrafficEventResponse]:
        """Return all events newest first using video timestamp."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, event_type, timestamp, confidence, severity,
                       explanation, camera_name, latitude, longitude,
                       evidence_image, status
                FROM events
                ORDER BY timestamp DESC, event_id ASC
                """
            ).fetchall()
        return [self._to_event(row) for row in rows]

    def update_status(
        self,
        event_id: str,
        status: EventStatus,
    ) -> TrafficEventResponse | None:
        """Apply a human Verify or Dismiss decision to one event."""
        if status not in {EventStatus.VERIFIED, EventStatus.DISMISSED}:
            raise ValueError("status must be VERIFIED or DISMISSED")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE events
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
                """,
                (status.value, event_id),
            )
        if cursor.rowcount == 0:
            return None
        return self.get(event_id)

    @staticmethod
    def _to_event(row: sqlite3.Row) -> TrafficEventResponse:
        return TrafficEventResponse.model_validate(dict(row))
