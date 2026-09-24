"""Small SQLite repository for CityEye AI traffic events."""

from __future__ import annotations

from contextlib import contextmanager
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import json
import base64
import math
import sqlite3
import time
from typing import Callable, Iterator
from uuid import uuid4

from app.auth import AuthenticatedUser

from app.schemas import (
    CitizenReportCreate,
    CitizenReportResponse,
    EventStatus,
    EventPageResponse,
    ReportStatus,
    TrafficEventIngest,
    TrafficEventResponse,
    TrafficObservation,
)


class DuplicateEventError(ValueError):
    """Raised when an event ID already exists in SQLite."""


class TrafficObservationRepository:
    """Persist sparse live-camera snapshots in the existing CityEye database."""

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
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS traffic_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    interval_start REAL NOT NULL CHECK (interval_start >= 0),
                    observed_at REAL NOT NULL CHECK (observed_at >= 0),
                    generation INTEGER NOT NULL CHECK (generation >= 0),
                    vehicles INTEGER NOT NULL CHECK (vehicles >= 0),
                    cars INTEGER NOT NULL CHECK (cars >= 0),
                    buses INTEGER NOT NULL CHECK (buses >= 0),
                    trucks INTEGER NOT NULL CHECK (trucks >= 0),
                    motorcycles INTEGER NOT NULL CHECK (motorcycles >= 0),
                    bicycles INTEGER NOT NULL CHECK (bicycles >= 0),
                    people INTEGER NOT NULL CHECK (people >= 0),
                    moving_vehicles INTEGER NOT NULL CHECK (moving_vehicles >= 0),
                    stationary_vehicles INTEGER NOT NULL CHECK (stationary_vehicles >= 0),
                    traffic_status TEXT NOT NULL,
                    capture_fps REAL NOT NULL CHECK (capture_fps >= 0),
                    ai_fps REAL NOT NULL CHECK (ai_fps >= 0),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(camera_id, interval_start)
                );
                CREATE INDEX IF NOT EXISTS idx_traffic_observations_camera_time
                ON traffic_observations(camera_id, observed_at);
                """
            )

    def add(self, observation: TrafficObservation) -> bool:
        payload = observation.model_dump()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO traffic_observations (
                    camera_id, interval_start, observed_at, generation,
                    vehicles, cars, buses, trucks, motorcycles, bicycles, people,
                    moving_vehicles, stationary_vehicles, traffic_status,
                    capture_fps, ai_fps
                ) VALUES (
                    :camera_id, :interval_start, :observed_at, :generation,
                    :vehicles, :cars, :buses, :trucks, :motorcycles, :bicycles,
                    :people, :moving_vehicles, :stationary_vehicles,
                    :traffic_status, :capture_fps, :ai_fps
                )
                """,
                payload,
            )
            return cursor.rowcount == 1

    def list_range(
        self, camera_id: str, start: float, end: float
    ) -> list[TrafficObservation]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT camera_id, interval_start, observed_at, generation,
                       vehicles, cars, buses, trucks, motorcycles, bicycles,
                       people, moving_vehicles, stationary_vehicles,
                       traffic_status, capture_fps, ai_fps
                FROM traffic_observations
                WHERE camera_id = ? AND observed_at BETWEEN ? AND ?
                ORDER BY observed_at ASC, id ASC
                """,
                (camera_id, start, end),
            ).fetchall()
        return [TrafficObservation.model_validate(dict(row)) for row in rows]

    def first_timestamp(self, camera_id: str) -> float | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT MIN(observed_at) FROM traffic_observations WHERE camera_id = ?",
                (camera_id,),
            ).fetchone()
        return float(row[0]) if row and row[0] is not None else None


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
                    details TEXT,
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

                CREATE TABLE IF NOT EXISTS events_v2 (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN ('WRONG_WAY', 'STOPPED_VEHICLE', 'CONGESTION', 'ROAD_BLOCKAGE')
                    ),
                    timestamp REAL NOT NULL CHECK (timestamp >= 0),
                    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
                    severity TEXT NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH')),
                    explanation TEXT NOT NULL,
                    camera_name TEXT NOT NULL,
                    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
                    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
                    evidence_image TEXT NOT NULL,
                    details_json TEXT,
                    status TEXT NOT NULL DEFAULT 'PROPOSED' CHECK (
                        status IN ('PROPOSED', 'VERIFIED', 'DISMISSED')
                    ),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_events_v2_timestamp ON events_v2(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_events_v2_status ON events_v2(status);
                INSERT OR IGNORE INTO events_v2 (
                    event_id,event_type,timestamp,confidence,severity,explanation,
                    camera_name,latitude,longitude,evidence_image,status,created_at,updated_at
                ) SELECT event_id,event_type,timestamp,confidence,severity,explanation,
                    camera_name,latitude,longitude,evidence_image,status,created_at,updated_at
                  FROM events;
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(events)")
            }
            if "details" not in columns:
                connection.execute("ALTER TABLE events ADD COLUMN details TEXT")

            event_columns = {row[1] for row in connection.execute("PRAGMA table_info(events_v2)")}
            for column in ("source_type", "source_id"):
                if column not in event_columns:
                    connection.execute(f"ALTER TABLE events_v2 ADD COLUMN {column} TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_events_history ON events_v2(timestamp DESC, event_id ASC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_events_source_history ON events_v2(source_type, source_id, timestamp DESC, event_id ASC)")

    def add(self, event: TrafficEventIngest) -> TrafficEventResponse:
        """Insert one AI-proposed event and reject duplicate IDs."""
        payload = event.model_dump(mode="json")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO events_v2 (
                        event_id, event_type, timestamp, confidence, severity,
                        explanation, camera_name, latitude, longitude,
                        evidence_image, details_json, status, source_type, source_id
                    ) VALUES (
                        :event_id, :event_type, :timestamp, :confidence, :severity,
                        :explanation, :camera_name, :latitude, :longitude,
                        :evidence_image, :details_json, :status, :source_type, :source_id
                    )
                    """,
                    {"source_type": None, "source_id": None, **payload, "details_json": json.dumps(payload.get("details")) if payload.get("details") is not None else None},
                )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed: events_v2.event_id" in str(exc):
                raise DuplicateEventError(
                    f"Event already exists: {event.event_id}"
                ) from exc
            raise

        stored = self.get(event.event_id)
        if stored is None:
            raise RuntimeError(f"Stored event could not be read: {event.event_id}")
        return stored

    def ingest_once(self, event: TrafficEventIngest) -> TrafficEventResponse:
        """Reconcile delivery retries by AI UUID, never overwrite a human decision."""
        stored = self.get(event.event_id)
        if stored is None:
            try:
                return self.add(event)
            except DuplicateEventError:
                stored = self.get(event.event_id)
        if stored is None:
            raise RuntimeError("Incident disappeared during ingestion")
        if stored.source_type is not None and (
            stored.source_type != event.source_type or stored.source_id != event.source_id
        ):
            raise ValueError("Event ID already belongs to a different source")
        if stored.source_type is None and event.source_type is not None:
            # Adopt earlier lazy-imported incidents without resetting their review.
            with self._connect() as connection:
                connection.execute(
                    "UPDATE events_v2 SET source_type = ?, source_id = ? WHERE event_id = ? AND source_type IS NULL",
                    (event.source_type, event.source_id, event.event_id),
                )
            stored = self.get(event.event_id)
        return stored

    def review_with_audit(
        self, event_id: str, status: EventStatus, actor: AuthenticatedUser, request_id: str,
    ) -> TrafficEventResponse | None:
        """Commit the decision and its audit entry together in the existing DB."""
        if status not in {EventStatus.VERIFIED, EventStatus.DISMISSED}:
            raise ValueError("status must be VERIFIED or DISMISSED")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT status FROM events_v2 WHERE event_id = ?", (event_id,),
            ).fetchone()
            if previous is None:
                return None
            connection.execute(
                "UPDATE events_v2 SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE event_id = ?",
                (status.value, event_id),
            )
            connection.execute(
                """INSERT INTO audit_log (audit_id, actor_user_id, actor_username, action,
                   target_type, target_id, previous_value, new_value, request_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), actor.user_id, actor.username,
                 "INCIDENT_VERIFIED" if status == EventStatus.VERIFIED else "INCIDENT_DISMISSED",
                 "traffic_event", event_id, previous["status"], status.value, request_id),
            )
            row = connection.execute("SELECT event_id, event_type, timestamp, confidence, severity, explanation, camera_name, latitude, longitude, evidence_image, details_json, status, source_type, source_id FROM events_v2 WHERE event_id = ?", (event_id,)).fetchone()
            return self._to_event(row)

    def get(self, event_id: str) -> TrafficEventResponse | None:
        """Return one event by ID or None when it does not exist."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT event_id, event_type, timestamp, confidence, severity,
                       explanation, camera_name, latitude, longitude,
                       evidence_image, details_json, status, source_type, source_id
                FROM events_v2
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
                       evidence_image, details_json, status, source_type, source_id
                FROM events_v2
                ORDER BY timestamp DESC, event_id ASC
                """
            ).fetchall()
        return [self._to_event(row) for row in rows]

    def page(self, *, limit: int = 100, cursor: str | None = None,
             source_type: str | None = None, source_id: str | None = None) -> EventPageResponse:
        """Bounded keyset page; new inserts cannot enter an existing snapshot."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        position = None
        watermark = None
        if cursor is not None:
            try:
                if len(cursor) > 2048:
                    raise ValueError()
                decoded = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                watermark, timestamp, event_id, previous_type, previous_id = decoded
                if (type(watermark) is not int or not 0 <= watermark < 2**63
                        or type(timestamp) not in (float, int) or not math.isfinite(timestamp) or timestamp < 0
                        or not isinstance(event_id, str) or not event_id
                        or (previous_type, previous_id) != (source_type, source_id)):
                    raise ValueError()
                position = (float(timestamp), event_id)
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError("Invalid cursor or source mismatch") from exc
        with self._connect() as connection:
            # One read transaction keeps count, watermark and rows coherent.
            connection.execute("BEGIN")
            if watermark is None:
                watermark = connection.execute("SELECT COALESCE(MAX(rowid), 0) FROM events_v2").fetchone()[0]
            clauses = ["rowid <= ?"]
            params: list[object] = [watermark]
            for column, value in (("source_type", source_type), ("source_id", source_id)):
                if value is not None:
                    clauses.append(f"{column} = ?")
                    params.append(value)
            where = " AND ".join(clauses)
            total = connection.execute(f"SELECT COUNT(*) FROM events_v2 WHERE {where}", params).fetchone()[0]
            if position is not None:
                where += " AND (timestamp < ? OR (timestamp = ? AND event_id > ?))"
                params.extend((position[0], position[0], position[1]))
            rows = connection.execute(f"""SELECT event_id,event_type,timestamp,confidence,severity,explanation,
                camera_name,latitude,longitude,evidence_image,details_json,status,source_type,source_id
                FROM events_v2 WHERE {where} ORDER BY timestamp DESC,event_id ASC LIMIT ?""",
                [*params, limit + 1]).fetchall()
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = base64.urlsafe_b64encode(json.dumps(
                [watermark, last["timestamp"], last["event_id"], source_type, source_id]
            ).encode()).decode()
        return EventPageResponse(events=[self._to_event(row) for row in rows[:limit]],
                                 total=total, next_cursor=next_cursor)

    def counts_for_source(self, source_id: str, start: float, end: float) -> list[sqlite3.Row]:
        """Aggregate persisted live incidents without loading their full history."""
        with self._connect() as connection:
            return connection.execute("""SELECT event_type, status, COUNT(*) AS count
                FROM events_v2 WHERE source_type = 'LIVE_CAMERA' AND source_id = ?
                AND timestamp BETWEEN ? AND ? GROUP BY event_type, status""",
                (source_id, start, end)).fetchall()

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
                UPDATE events_v2
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
        payload = dict(row)
        details_json = payload.pop("details_json", None)
        if details_json:
            payload["details"] = json.loads(details_json)
        return TrafficEventResponse.model_validate(payload)


class CitizenReportRepository:
    """Persist citizen traffic reports in the local SQLite database."""

    def __init__(
        self,
        database_path: Path,
        clock: Callable[[], float] = time.time,
        id_factory: Callable[[], object] = uuid4,
        min_distinct_users: int = 5,
        cluster_radius_meters: float = 100.0,
        cluster_window_seconds: float = 15 * 60,
    ) -> None:
        if min_distinct_users < 2:
            raise ValueError("min_distinct_users must be at least 2")
        if cluster_radius_meters <= 0:
            raise ValueError("cluster_radius_meters must be positive")
        if cluster_window_seconds <= 0:
            raise ValueError("cluster_window_seconds must be positive")
        self.database_path = Path(database_path)
        self.clock = clock
        self.id_factory = id_factory
        self.min_distinct_users = min_distinct_users
        self.cluster_radius_meters = cluster_radius_meters
        self.cluster_window_seconds = cluster_window_seconds

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
        """Create the citizen_reports table and lookup index."""
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS citizen_reports (
                    report_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL CHECK (
                        category IN (
                            'CONGESTION', 'ROAD_HAZARD', 'BLOCKED_ROAD', 'OTHER'
                        )
                    ),
                    description TEXT NOT NULL,
                    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
                    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
                    demo_user_id TEXT NOT NULL,
                    reported_at REAL NOT NULL CHECK (reported_at >= 0),
                    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
                        status IN ('PENDING', 'COMMUNITY_CONFIRMED')
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_citizen_reports_cluster_lookup
                ON citizen_reports(category, reported_at DESC);
                """
            )

            # Existing reports have untrusted client identities. Never count them
            # toward consensus from authenticated accounts after upgrading.
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(citizen_reports)")}
            if "authenticated_user_id" not in columns:
                connection.execute("ALTER TABLE citizen_reports ADD COLUMN authenticated_user_id TEXT")

    def add(
        self, report: CitizenReportCreate, *, authenticated_user_id: str | None = None
    ) -> CitizenReportResponse:
        """Store one report and confirm a compatible five-user cluster."""
        payload = report.model_dump(mode="json")
        if authenticated_user_id is not None:
            payload["demo_user_id"] = authenticated_user_id
        payload.update(
            {
                "report_id": str(self.id_factory()),
                "reported_at": float(self.clock()),
                "status": ReportStatus.PENDING.value,
            }
        )
        stored_report = CitizenReportResponse.model_validate(payload)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO citizen_reports (
                    report_id, category, description, latitude, longitude,
                    demo_user_id, reported_at, status, authenticated_user_id
                ) VALUES (
                    :report_id, :category, :description, :latitude, :longitude,
                    :demo_user_id, :reported_at, :status, :authenticated_user_id
                )
                """,
                {**stored_report.model_dump(mode="json"), "authenticated_user_id": authenticated_user_id},
            )
            compatible_reports = self._compatible_reports(
                connection,
                stored_report,
                authenticated=authenticated_user_id is not None,
            )
            distinct_users = {
                compatible.demo_user_id for compatible in compatible_reports
            }
            if len(distinct_users) >= self.min_distinct_users:
                report_ids = [compatible.report_id for compatible in compatible_reports]
                placeholders = ", ".join("?" for _ in report_ids)
                connection.execute(
                    f"""
                    UPDATE citizen_reports
                    SET status = ?
                    WHERE report_id IN ({placeholders})
                    """,
                    (ReportStatus.COMMUNITY_CONFIRMED.value, *report_ids),
                )

            row = connection.execute(
                """
                SELECT report_id, category, description, latitude, longitude,
                       demo_user_id, reported_at, status
                FROM citizen_reports
                WHERE report_id = ?
                """,
                (stored_report.report_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Stored report could not be read: {stored_report.report_id}")
        return self._to_report(row)

    def get(self, report_id: str) -> CitizenReportResponse | None:
        """Return one report by ID or None."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT report_id, category, description, latitude, longitude,
                       demo_user_id, reported_at, status
                FROM citizen_reports
                WHERE report_id = ?
                """,
                (report_id,),
            ).fetchone()
        return self._to_report(row) if row is not None else None

    def list(self) -> list[CitizenReportResponse]:
        """Return all reports newest first."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT report_id, category, description, latitude, longitude,
                       demo_user_id, reported_at, status
                FROM citizen_reports
                ORDER BY reported_at DESC, report_id ASC
                """
            ).fetchall()
        return [self._to_report(row) for row in rows]

    def _compatible_reports(
        self,
        connection: sqlite3.Connection,
        report: CitizenReportResponse,
        *, authenticated: bool = False,
    ) -> list[CitizenReportResponse]:
        earliest_time = report.reported_at - self.cluster_window_seconds
        rows = connection.execute(
            """
            SELECT report_id, category, description, latitude, longitude,
                   demo_user_id, reported_at, status
            FROM citizen_reports
            WHERE category = ?
              AND reported_at BETWEEN ? AND ?
              AND (authenticated_user_id IS NOT NULL) = ?
            """,
            (report.category.value, earliest_time, report.reported_at, int(authenticated)),
        ).fetchall()
        candidates = [self._to_report(row) for row in rows]
        return [
            candidate
            for candidate in candidates
            if haversine_distance_meters(
                report.latitude,
                report.longitude,
                candidate.latitude,
                candidate.longitude,
            )
            <= self.cluster_radius_meters
        ]

    @staticmethod
    def _to_report(row: sqlite3.Row) -> CitizenReportResponse:
        return CitizenReportResponse.model_validate(dict(row))


def haversine_distance_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return the great-circle distance between two coordinates in meters."""
    earth_radius_meters = 6_371_000.0
    latitude_a_rad = radians(latitude_a)
    latitude_b_rad = radians(latitude_b)
    latitude_delta = latitude_b_rad - latitude_a_rad
    longitude_delta = radians(longitude_b - longitude_a)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(latitude_a_rad)
        * cos(latitude_b_rad)
        * sin(longitude_delta / 2) ** 2
    )
    normalized_haversine = min(1.0, max(0.0, haversine))
    return 2 * earth_radius_meters * asin(sqrt(normalized_haversine))
