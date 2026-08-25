"""FastAPI entry point for the CityEye AI MVP Backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from pathlib import PurePosixPath
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.database import DuplicateEventError, EventRepository
from app.schemas import (
    EventListResponse,
    EventStatus,
    TrafficEventIngest,
    TrafficEventResponse,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "cityeye.db"
DEFAULT_EVIDENCE_DIR = BACKEND_ROOT.parent / "ai" / "output" / "evidence"


class HealthResponse(BaseModel):
    """Stable response returned by the health endpoint."""

    status: str
    service: str


def get_event_repository(request: Request) -> EventRepository:
    """Return the repository initialized by the FastAPI lifespan."""
    return request.app.state.event_repository


def update_event_status(
    repository: EventRepository,
    event_id: str,
    status_value: EventStatus,
) -> TrafficEventResponse:
    """Update one event or translate a missing row to HTTP 404."""
    event = repository.update_status(event_id, status_value)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event not found: {event_id}",
        )
    return event


def resolve_evidence_path(evidence_dir: Path, filename: str) -> Path:
    """Resolve one safe JPG inside evidence_dir or raise an HTTP error."""
    relative_path = PurePosixPath(filename)
    if (
        not filename.strip()
        or "\\" in filename
        or len(relative_path.parts) != 1
        or relative_path.name in {".", ".."}
        or relative_path.suffix.lower() not in {".jpg", ".jpeg"}
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evidence filename must be a safe JPG name",
        )

    evidence_root = evidence_dir.resolve()
    evidence_path = (evidence_root / filename).resolve()
    if evidence_path.parent != evidence_root:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evidence filename must remain inside the evidence directory",
        )
    if not evidence_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence image not found: {filename}",
        )
    return evidence_path


def create_app(
    database_path: Path | None = None,
    evidence_dir: Path | None = None,
) -> FastAPI:
    """Build an app using the selected SQLite file."""
    selected_database_path = database_path or Path(
        os.getenv("CITYEYE_DATABASE_PATH", DEFAULT_DATABASE_PATH)
    )
    selected_evidence_dir = evidence_dir or Path(
        os.getenv("CITYEYE_EVIDENCE_DIR", DEFAULT_EVIDENCE_DIR)
    )
    repository = EventRepository(selected_database_path)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        repository.initialize()
        application.state.event_repository = repository
        yield

    application = FastAPI(
        title="CityEye AI Backend",
        description="Local MVP API for reviewed traffic events and citizen reports.",
        version="0.2.0",
        lifespan=lifespan,
    )

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Confirm that the local API process is running."""
        return HealthResponse(status="ok", service="cityeye-ai-backend")

    @application.post(
        "/api/events/ingest",
        response_model=TrafficEventResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["events"],
    )
    def ingest_event(
        event: TrafficEventIngest,
        event_repository: EventRepository = Depends(get_event_repository),
    ) -> TrafficEventResponse:
        """Validate and store one AI-proposed traffic event."""
        try:
            return event_repository.add(event)
        except DuplicateEventError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    @application.get(
        "/api/events",
        response_model=EventListResponse,
        tags=["events"],
    )
    def list_events(
        event_repository: EventRepository = Depends(get_event_repository),
    ) -> EventListResponse:
        """Return all events for two-second dashboard polling."""
        events = event_repository.list()
        return EventListResponse(events=events, total=len(events))

    @application.get(
        "/api/events/{event_id}",
        response_model=TrafficEventResponse,
        tags=["events"],
    )
    def get_event(
        event_id: str,
        event_repository: EventRepository = Depends(get_event_repository),
    ) -> TrafficEventResponse:
        """Return one traffic event or 404."""
        event = event_repository.get(event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event not found: {event_id}",
            )
        return event

    @application.post(
        "/api/events/{event_id}/verify",
        response_model=TrafficEventResponse,
        tags=["events"],
    )
    def verify_event(
        event_id: str,
        event_repository: EventRepository = Depends(get_event_repository),
    ) -> TrafficEventResponse:
        """Apply a municipal human verification decision."""
        return update_event_status(
            event_repository,
            event_id,
            EventStatus.VERIFIED,
        )

    @application.post(
        "/api/events/{event_id}/dismiss",
        response_model=TrafficEventResponse,
        tags=["events"],
    )
    def dismiss_event(
        event_id: str,
        event_repository: EventRepository = Depends(get_event_repository),
    ) -> TrafficEventResponse:
        """Apply a municipal human dismissal decision."""
        return update_event_status(
            event_repository,
            event_id,
            EventStatus.DISMISSED,
        )

    @application.get(
        "/evidence/{filename}",
        response_class=FileResponse,
        tags=["evidence"],
    )
    def get_evidence(filename: str) -> FileResponse:
        """Serve one municipal evidence JPG without exposing other files."""
        evidence_path = resolve_evidence_path(selected_evidence_dir, filename)
        return FileResponse(
            evidence_path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return application


app = create_app()
