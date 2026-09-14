"""FastAPI entry point for the CityEye AI MVP Backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from pathlib import PurePosixPath
from time import perf_counter
from typing import AsyncIterator
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.analysis import read_analysis_summary, read_analysis_timeline, resolve_annotated_video
from app.database import (
    CitizenReportRepository,
    DuplicateEventError,
    EventRepository,
)
from app.observability import (
    artifact_health,
    configure_logging,
    database_health,
    safe_request_id,
)
from app.security import SECURITY_HEADERS, SecuritySettings
from app.schemas import (
    AnalysisTimeline,
    AnalysisSummary,
    CitizenReportCreate,
    CitizenReportListResponse,
    CitizenReportResponse,
    EventListResponse,
    EventStatus,
    TrafficEventIngest,
    TrafficEventResponse,
    ScenarioInfo,
    ScenarioListResponse,
)
from app.scenarios import SCENARIOS, read_scenario_events, scenario_directory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "cityeye.db"
DEFAULT_EVIDENCE_DIR = BACKEND_ROOT.parent / "ai" / "output" / "evidence"
DEFAULT_AI_OUTPUT_DIR = BACKEND_ROOT.parent / "ai" / "output"
DEFAULT_SCENARIO_OUTPUT_ROOT = BACKEND_ROOT.parent / "ai" / "scenario_outputs"


class HealthResponse(BaseModel):
    """Stable response returned by the health endpoint."""

    status: str
    service: str


class ReadinessResponse(BaseModel):
    """Dependency-aware service readiness returned to operators."""

    status: str
    service: str
    environment: str
    components: dict[str, dict[str, str]]


def get_event_repository(request: Request) -> EventRepository:
    """Return the repository initialized by the FastAPI lifespan."""
    return request.app.state.event_repository


def get_citizen_report_repository(request: Request) -> CitizenReportRepository:
    """Return the citizen-report repository initialized at startup."""
    return request.app.state.citizen_report_repository


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
    ai_output_dir: Path | None = None,
    scenario_output_root: Path | None = None,
) -> FastAPI:
    """Build an app using the selected SQLite file."""
    selected_database_path = database_path or Path(
        os.getenv("CITYEYE_DATABASE_PATH", DEFAULT_DATABASE_PATH)
    )
    selected_evidence_dir = evidence_dir or Path(
        os.getenv("CITYEYE_EVIDENCE_DIR", DEFAULT_EVIDENCE_DIR)
    )
    selected_ai_output_dir = ai_output_dir or Path(
        os.getenv("CITYEYE_AI_OUTPUT_DIR", DEFAULT_AI_OUTPUT_DIR)
    )
    selected_scenario_root = scenario_output_root or Path(
        os.getenv("CITYEYE_SCENARIO_OUTPUT_ROOT", DEFAULT_SCENARIO_OUTPUT_ROOT)
    )
    security_settings = SecuritySettings.from_environment()
    environment = security_settings.environment
    logger = configure_logging()
    repository = EventRepository(selected_database_path)
    citizen_report_repository = CitizenReportRepository(selected_database_path)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        repository.initialize()
        citizen_report_repository.initialize()
        application.state.event_repository = repository
        application.state.citizen_report_repository = citizen_report_repository
        yield

    application = FastAPI(
        title="CityEye AI Backend",
        description="Local MVP API for reviewed traffic events and citizen reports.",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs" if security_settings.docs_enabled else None,
        redoc_url="/redoc" if security_settings.docs_enabled else None,
        openapi_url="/openapi.json" if security_settings.docs_enabled else None,
    )

    if security_settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(security_settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    if security_settings.trusted_hosts != ("*",):
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=list(security_settings.trusted_hosts),
        )

    @application.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = safe_request_id(request.headers.get("X-Request-ID")) or str(uuid4())
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "environment": environment,
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
            raise
        response.headers["X-Request-ID"] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        logger.info(
            "request_completed",
            extra={
                "environment": environment,
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            },
        )
        return response

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Confirm that the local API process is running."""
        return HealthResponse(status="ok", service="cityeye-ai-backend")

    @application.get("/health/live", response_model=HealthResponse, tags=["system"])
    def liveness() -> HealthResponse:
        """Confirm that the API process is alive without checking dependencies."""
        return HealthResponse(status="ok", service="cityeye-ai-backend")

    @application.get(
        "/health/ready",
        response_model=ReadinessResponse,
        responses={503: {"model": ReadinessResponse}},
        tags=["system"],
    )
    def readiness() -> ReadinessResponse:
        """Check required dependencies and report optional AI artifact state."""
        components = {
            "database": database_health(selected_database_path),
            "ai_artifacts": artifact_health(selected_ai_output_dir),
        }
        ready = components["database"]["status"] == "ok"
        payload = ReadinessResponse(
            status="ready" if ready else "not_ready",
            service="cityeye-ai-backend",
            environment=environment,
            components=components,
        )
        if not ready:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=payload.model_dump())
        return payload

    @application.get(
        "/api/analysis/summary",
        response_model=AnalysisSummary,
        tags=["analysis"],
    )
    def analysis_summary() -> AnalysisSummary:
        """Return vehicle count and availability from real AI output files."""
        return read_analysis_summary(selected_ai_output_dir)

    @application.get(
        "/api/analysis/timeline",
        response_model=AnalysisTimeline,
        tags=["analysis"],
    )
    def analysis_timeline() -> AnalysisTimeline:
        """Return real frame-by-frame counts synchronized with the processed video."""
        return read_analysis_timeline(selected_ai_output_dir)

    @application.get(
        "/media/annotated.mp4",
        response_class=FileResponse,
        tags=["analysis"],
    )
    def annotated_video() -> FileResponse:
        """Serve the fixed processed video without accepting a user path."""
        video_path = resolve_annotated_video(selected_ai_output_dir)
        if video_path is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Annotated video not found. Run the AI pipeline first.",
            )
        return FileResponse(
            video_path,
            media_type="video/mp4",
            headers={"Cache-Control": "no-store"},
        )

    def require_scenario(scenario_id: str) -> Path:
        directory = scenario_directory(selected_scenario_root, scenario_id)
        if directory is None:
            raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id}")
        return directory

    @application.get("/api/scenarios", response_model=ScenarioListResponse, tags=["scenarios"])
    def list_scenarios() -> ScenarioListResponse:
        return ScenarioListResponse(scenarios=list(SCENARIOS.values()))

    @application.get("/api/scenarios/{scenario_id}/analysis/summary", response_model=AnalysisSummary, tags=["scenarios"])
    def scenario_summary(scenario_id: str) -> AnalysisSummary:
        return read_analysis_summary(require_scenario(scenario_id))

    @application.get("/api/scenarios/{scenario_id}/analysis/timeline", response_model=AnalysisTimeline, tags=["scenarios"])
    def scenario_timeline(scenario_id: str) -> AnalysisTimeline:
        return read_analysis_timeline(require_scenario(scenario_id))

    @application.get("/api/scenarios/{scenario_id}/events", response_model=EventListResponse, tags=["scenarios"])
    def scenario_events(scenario_id: str) -> EventListResponse:
        try:
            events = read_scenario_events(require_scenario(scenario_id))
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        merged = [repository.get(event.event_id) or event for event in events]
        return EventListResponse(events=merged, total=len(merged))

    def review_scenario_event(scenario_id: str, event_id: str, decision: EventStatus) -> TrafficEventResponse:
        events = read_scenario_events(require_scenario(scenario_id))
        source = next((item for item in events if item.event_id == event_id), None)
        if source is None:
            raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")
        if repository.get(event_id) is None:
            repository.add(TrafficEventIngest.model_validate(source.model_dump()))
        return update_event_status(repository, event_id, decision)

    @application.post("/api/scenarios/{scenario_id}/events/{event_id}/verify", response_model=TrafficEventResponse, tags=["scenarios"])
    def verify_scenario_event(scenario_id: str, event_id: str) -> TrafficEventResponse:
        return review_scenario_event(scenario_id, event_id, EventStatus.VERIFIED)

    @application.post("/api/scenarios/{scenario_id}/events/{event_id}/dismiss", response_model=TrafficEventResponse, tags=["scenarios"])
    def dismiss_scenario_event(scenario_id: str, event_id: str) -> TrafficEventResponse:
        return review_scenario_event(scenario_id, event_id, EventStatus.DISMISSED)

    @application.get("/media/scenarios/{scenario_id}/annotated.mp4", response_class=FileResponse, tags=["scenarios"])
    def scenario_video(scenario_id: str) -> FileResponse:
        video_path = resolve_annotated_video(require_scenario(scenario_id))
        if video_path is None:
            raise HTTPException(status_code=404, detail="Scenario video is unavailable")
        return FileResponse(video_path, media_type="video/mp4", headers={"Cache-Control": "no-store"})

    @application.get("/evidence/scenarios/{scenario_id}/{filename}", response_class=FileResponse, tags=["scenarios"])
    def scenario_evidence(scenario_id: str, filename: str) -> FileResponse:
        path = resolve_evidence_path(require_scenario(scenario_id) / "evidence", filename)
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

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

    @application.post(
        "/api/citizen-reports",
        response_model=CitizenReportResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["citizen reports"],
    )
    def create_citizen_report(
        report: CitizenReportCreate,
        report_repository: CitizenReportRepository = Depends(
            get_citizen_report_repository
        ),
    ) -> CitizenReportResponse:
        """Store one citizen report with Backend-generated metadata."""
        return report_repository.add(report)

    @application.get(
        "/api/citizen-reports",
        response_model=CitizenReportListResponse,
        tags=["citizen reports"],
    )
    def list_citizen_reports(
        report_repository: CitizenReportRepository = Depends(
            get_citizen_report_repository
        ),
    ) -> CitizenReportListResponse:
        """Return citizen reports newest first for map polling."""
        reports = report_repository.list()
        return CitizenReportListResponse(reports=reports, total=len(reports))

    @application.get(
        "/api/citizen-reports/{report_id}",
        response_model=CitizenReportResponse,
        tags=["citizen reports"],
    )
    def get_citizen_report(
        report_id: str,
        report_repository: CitizenReportRepository = Depends(
            get_citizen_report_repository
        ),
    ) -> CitizenReportResponse:
        """Return one citizen report or 404."""
        report = report_repository.get(report_id)
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Citizen report not found: {report_id}",
            )
        return report

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
