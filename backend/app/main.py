"""FastAPI entry point for the CityEye AI MVP Backend."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hmac
import logging
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
from time import perf_counter
from typing import AsyncIterator, Literal
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.analysis import read_analysis_summary, read_analysis_timeline, resolve_annotated_video
from app.auth import (
    AuthenticatedUser,
    AuthRepository,
    AuthSettings,
    read_secret_file,
)
from app.database import (
    CitizenReportRepository,
    DuplicateEventError,
    EventRepository,
    TrafficObservationRepository,
)
from app.live_incidents import LiveIncidentImporter
from app.live_camera import mjpeg_frames, read_camera_health, read_live_snapshot
from app.operational_analytics import (
    DEFAULT_SAMPLE_INTERVAL_SECONDS,
    collect_live_observation,
    query_operational_analytics,
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
    EventPageResponse,
    EventStatus,
    TrafficEventIngest,
    TrafficEventResponse,
    ScenarioInfo,
    ScenarioListResponse,
    CameraHealthResponse,
    LiveMetricsSnapshot,
    OperationalAnalyticsResponse,
)
from app.scenarios import SCENARIOS, read_scenario_events, scenario_directory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "cityeye.db"
DEFAULT_EVIDENCE_DIR = BACKEND_ROOT.parent / "ai" / "output" / "evidence"
DEFAULT_AI_OUTPUT_DIR = BACKEND_ROOT.parent / "ai" / "output"
DEFAULT_SCENARIO_OUTPUT_ROOT = BACKEND_ROOT.parent / "ai" / "scenario_outputs"
DEFAULT_LIVE_OUTPUT_DIR = BACKEND_ROOT.parent / "ai" / "live_output"
LIVE_CAMERA_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


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


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    user_id: str
    username: str
    role: str
    active: bool = True


class LoginResponse(BaseModel):
    expires_at: float
    user: UserResponse


class SessionResponse(BaseModel):
    auth_required: bool
    user: UserResponse | None


class LogoutResponse(BaseModel):
    status: str


class AuditListResponse(BaseModel):
    entries: list[dict[str, object]]
    total: int


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["CITIZEN", "EMPLOYEE", "ADMIN"]


class UserUpdate(BaseModel):
    role: Literal["CITIZEN", "EMPLOYEE", "ADMIN"] | None = None
    active: bool | None = None


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


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


def resolve_live_camera_directory(root: Path, camera_id: str) -> Path:
    """Resolve one camera output without allowing path traversal."""
    if not LIVE_CAMERA_ID_PATTERN.fullmatch(camera_id):
        raise HTTPException(status_code=400, detail="Invalid live camera ID")
    directory = (root / camera_id).resolve()
    if directory.parent != root.resolve():
        raise HTTPException(status_code=400, detail="Invalid live camera directory")
    return directory


def create_app(
    database_path: Path | None = None,
    evidence_dir: Path | None = None,
    ai_output_dir: Path | None = None,
    scenario_output_root: Path | None = None,
    live_output_dir: Path | None = None,
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
    selected_live_output_dir = live_output_dir or Path(
        os.getenv("CITYEYE_LIVE_OUTPUT_DIR", DEFAULT_LIVE_OUTPUT_DIR)
    )
    security_settings = SecuritySettings.from_environment()
    environment = security_settings.environment
    auth_settings = AuthSettings.from_environment(environment)
    logger = configure_logging()
    repository = EventRepository(selected_database_path)
    citizen_report_repository = CitizenReportRepository(selected_database_path)
    auth_repository = AuthRepository(selected_database_path)
    traffic_observation_repository = TrafficObservationRepository(
        selected_database_path
    )
    ingest_token: str | None = None
    observation_interval = int(os.getenv(
        "CITYEYE_ANALYTICS_SAMPLE_INTERVAL_SECONDS",
        str(DEFAULT_SAMPLE_INTERVAL_SECONDS),
    ))
    if observation_interval <= 0:
        raise ValueError("CITYEYE_ANALYTICS_SAMPLE_INTERVAL_SECONDS must be positive")
    collector_poll_seconds = float(os.getenv(
        "CITYEYE_ANALYTICS_COLLECTOR_POLL_SECONDS", "5"
    ))
    if collector_poll_seconds <= 0:
        raise ValueError("CITYEYE_ANALYTICS_COLLECTOR_POLL_SECONDS must be positive")
    configured_live_camera_ids = tuple(
        camera_id.strip()
        for camera_id in os.getenv("CITYEYE_LIVE_CAMERA_IDS", "camera-3").split(",")
        if camera_id.strip()
    )

    incident_importer = LiveIncidentImporter(selected_live_output_dir, repository)

    async def collect_live_incidents(stop: asyncio.Event) -> None:
        while not stop.is_set():
            for camera_id in configured_live_camera_ids:
                await asyncio.to_thread(incident_importer.sync_safely, camera_id)
            try:
                await asyncio.wait_for(stop.wait(), timeout=2.0)
            except TimeoutError:
                pass

    async def collect_traffic_observations(stop: asyncio.Event) -> None:
        while not stop.is_set():
            for camera_id in configured_live_camera_ids:
                await asyncio.to_thread(
                    collect_live_observation,
                    camera_id=camera_id,
                    directory=selected_live_output_dir / camera_id,
                    repository=traffic_observation_repository,
                    interval_seconds=observation_interval,
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=collector_poll_seconds)
            except TimeoutError:
                pass

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        nonlocal ingest_token
        repository.initialize()
        citizen_report_repository.initialize()
        traffic_observation_repository.initialize()
        auth_repository.initialize()
        if auth_settings.bootstrap_username and auth_repository.user_count() == 0:
            password = read_secret_file(
                auth_settings.bootstrap_password_file,
                "bootstrap administrator password",
            )
            if password is None:
                raise RuntimeError("Bootstrap username requires a password secret file")
            auth_repository.create_user(
                auth_settings.bootstrap_username,
                password,
                auth_settings.bootstrap_role,
            )
        if auth_settings.required and auth_repository.user_count() == 0:
            raise RuntimeError(
                "Authentication is required but no users exist; configure bootstrap admin secrets"
            )
        if auth_settings.required:
            ingest_token = read_secret_file(
                auth_settings.ingest_token_file, "AI ingest token"
            )
        application.state.event_repository = repository
        application.state.citizen_report_repository = citizen_report_repository
        application.state.traffic_observation_repository = (
            traffic_observation_repository
        )
        # Finish one replay at startup, including proposals created while offline.
        for camera_id in configured_live_camera_ids:
            await asyncio.to_thread(incident_importer.sync_safely, camera_id)
        incident_stop = asyncio.Event()
        incident_task = asyncio.create_task(collect_live_incidents(incident_stop))
        collector_stop = asyncio.Event()
        collector_task = asyncio.create_task(
            collect_traffic_observations(collector_stop)
        )
        try:
            yield
        finally:
            collector_stop.set()
            incident_stop.set()
            await asyncio.gather(collector_task, incident_task)

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
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-CityEye-Ingest-Token",
                "X-Request-ID",
            ],
            expose_headers=["X-Request-ID"],
        )
    if security_settings.trusted_hosts != ("*",):
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=list(security_settings.trusted_hosts),
        )

    async def request_logging(request: Request, call_next):
        request_id = safe_request_id(request.headers.get("X-Request-ID")) or str(uuid4())
        request.state.request_id = request_id
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
        if request.url.path.startswith(("/api/", "/media/", "/evidence/")):
            response.headers["Cache-Control"] = "no-store"
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

    def token_from_header(authorization: str | None) -> str | None:
        if not authorization:
            return None
        scheme, separator, token = authorization.partition(" ")
        if separator and scheme.lower() == "bearer" and token:
            return token
        return None

    session_cookie_name = "cityeye_session"

    def optional_user(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=session_cookie_name),
    ) -> AuthenticatedUser | None:
        token = token_from_header(authorization) or session_cookie
        return auth_repository.resolve_session(token) if token else None

    def require_user(
        user: AuthenticatedUser | None = Depends(optional_user),
    ) -> AuthenticatedUser:
        if not auth_settings.required:
            return AuthenticatedUser("demo-access", "Demo Operator", "ADMIN")
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    def require_roles(*roles: str):
        def dependency(user: AuthenticatedUser = Depends(require_user)) -> AuthenticatedUser:
            if user.role not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient role",
                )
            return user

        return dependency

    def require_ingest_token(
        supplied_token: str | None = Header(default=None, alias="X-CityEye-Ingest-Token"),
    ) -> None:
        if not auth_settings.required:
            return
        if ingest_token is None or supplied_token is None:
            raise HTTPException(status_code=401, detail="Valid AI ingest token required")
        if not hmac.compare_digest(supplied_token, ingest_token):
            raise HTTPException(status_code=401, detail="Valid AI ingest token required")

    @application.middleware("http")
    async def protect_product_surfaces(request: Request, call_next):
        """Enforce a valid human session before product data leaves the API."""
        path = request.url.path
        public = (
            path in {"/health", "/health/live", "/health/ready", "/api/auth/login", "/api/auth/session"}
            or path.startswith("/docs")
            or path == "/openapi.json"
            or (path == "/api/events/ingest" and request.method == "POST")
        )
        protected = path.startswith(("/api/", "/media/", "/evidence/"))
        if auth_settings.required and request.method not in {"GET", "HEAD", "OPTIONS"}:
            # SameSite is defense in depth; reject browser writes from other origins.
            origin = request.headers.get("origin")
            allowed_origins = {*security_settings.cors_origins, str(request.base_url).rstrip("/")}
            if origin and origin not in allowed_origins:
                return JSONResponse(status_code=403, content={"detail": "Untrusted request origin"})
        if auth_settings.required and protected and request.method != "OPTIONS":
            token = token_from_header(request.headers.get("Authorization")) or request.cookies.get(session_cookie_name)
            user = auth_repository.resolve_session(token) if token else None
            if not public and user is None:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Authentication required"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            citizen_surface = (
                path in {"/api/auth/login", "/api/auth/session", "/api/auth/logout"}
                or (path == "/api/citizen-reports" and request.method in {"GET", "HEAD", "POST"})
                or (re.fullmatch(r"/api/citizen-reports/[^/]+", path) is not None
                    and request.method in {"GET", "HEAD"})
            )
            if user is not None and user.role == "CITIZEN" and not citizen_surface:
                return JSONResponse(status_code=403, content={"detail": "Citizen access is limited to the map"})
        response = await call_next(request)
        if protected:
            response.headers["Cache-Control"] = "no-store"
        return response

    # Logging/security headers must also wrap rejected authentication requests.
    application.middleware("http")(request_logging)

    @application.post("/api/auth/login", response_model=LoginResponse, tags=["authentication"])
    def login(credentials: LoginRequest, request: Request, response: Response) -> LoginResponse:
        if not auth_settings.required:
            raise HTTPException(status_code=409, detail="Authentication is disabled in this environment")
        user = auth_repository.authenticate(credentials.username, credentials.password)
        if user is None:
            auth_repository.record_audit(
                actor=AuthenticatedUser("anonymous", "anonymous", "CITIZEN"),
                action="LOGIN_FAILED",
                target_type="authentication",
                target_id="session",
                previous_value=None,
                new_value=None,
                request_id=request.state.request_id,
            )
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token, expires_at = auth_repository.create_session(
            user, auth_settings.session_ttl_seconds
        )
        response.set_cookie(
            key=session_cookie_name,
            value=token,
            max_age=auth_settings.session_ttl_seconds,
            httponly=True,
            secure=environment == "production",
            samesite="strict",
            path="/",
        )
        auth_repository.record_audit(
            actor=user, action="LOGIN_SUCCEEDED", target_type="authentication",
            target_id="session", previous_value=None, new_value=None,
            request_id=request.state.request_id,
        )
        return LoginResponse(expires_at=expires_at, user=UserResponse(**user.__dict__))

    @application.get("/api/auth/session", response_model=SessionResponse, tags=["authentication"])
    def auth_session(user: AuthenticatedUser | None = Depends(optional_user)) -> SessionResponse:
        if not auth_settings.required:
            demo = AuthenticatedUser("demo-access", "Demo Operator", "ADMIN")
            return SessionResponse(auth_required=False, user=UserResponse(**demo.__dict__))
        return SessionResponse(
            auth_required=True,
            user=UserResponse(**user.__dict__) if user else None,
        )

    @application.post(
        "/api/auth/logout", response_model=LogoutResponse, tags=["authentication"]
    )
    def logout(
        request: Request,
        response: Response,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=session_cookie_name),
        user: AuthenticatedUser = Depends(require_user),
    ) -> LogoutResponse:
        token = token_from_header(authorization) or session_cookie
        if token:
            auth_repository.revoke_session(token)
        response.delete_cookie(session_cookie_name, path="/", samesite="strict")
        auth_repository.record_audit(
            actor=user, action="LOGOUT", target_type="authentication",
            target_id="session", previous_value=None, new_value=None,
            request_id=request.state.request_id,
        )
        return LogoutResponse(status="ok")

    @application.get("/api/audit", response_model=AuditListResponse, tags=["audit"])
    def audit_log(
        _user: AuthenticatedUser = Depends(require_roles("EMPLOYEE", "ADMIN")),
    ) -> AuditListResponse:
        entries = auth_repository.list_audit()
        return AuditListResponse(entries=entries, total=len(entries))

    @application.get("/api/users", response_model=UserListResponse, tags=["users"])
    def list_users(
        _admin: AuthenticatedUser = Depends(require_roles("ADMIN")),
    ) -> UserListResponse:
        users = [UserResponse(**user.__dict__) for user in auth_repository.list_users()]
        return UserListResponse(users=users, total=len(users))

    @application.post(
        "/api/users",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["users"],
    )
    def create_user(
        payload: UserCreate,
        request: Request,
        admin: AuthenticatedUser = Depends(require_roles("ADMIN")),
    ) -> UserResponse:
        try:
            user = auth_repository.create_user(
                payload.username, payload.password, payload.role
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        auth_repository.record_audit(
            actor=admin,
            action="USER_CREATED",
            target_type="user",
            target_id=user.user_id,
            previous_value=None,
            new_value=user.role,
            request_id=request.state.request_id,
        )
        return UserResponse(**user.__dict__)

    @application.patch("/api/users/{user_id}", response_model=UserResponse, tags=["users"])
    def update_user(
        user_id: str,
        payload: UserUpdate,
        request: Request,
        admin: AuthenticatedUser = Depends(require_roles("ADMIN")),
    ) -> UserResponse:
        try:
            updated = auth_repository.update_user(
                user_id, role=payload.role, active=payload.active
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="User not found")
        auth_repository.record_audit(
            actor=admin, action="USER_ACCESS_UPDATED", target_type="user",
            target_id=user_id, previous_value=None,
            new_value=f"role={updated.role};active={updated.active}",
            request_id=request.state.request_id,
        )
        return UserResponse(**updated.__dict__)

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
        "/api/live-camera/status",
        response_model=CameraHealthResponse,
        tags=["live camera"],
    )
    def live_camera_status() -> CameraHealthResponse:
        try:
            return read_camera_health(selected_live_output_dir)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @application.get(
        "/api/live-camera/metrics",
        response_model=LiveMetricsSnapshot,
        tags=["live camera"],
    )
    def live_camera_metrics() -> LiveMetricsSnapshot:
        try:
            return read_live_snapshot(selected_live_output_dir, read_camera_health(selected_live_output_dir).camera_id)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @application.get("/api/live-camera/events", response_model=EventListResponse, tags=["live camera"])
    def live_camera_events() -> EventListResponse:
        try:
            events = read_scenario_events(selected_live_output_dir)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        merged = [repository.get(event.event_id) or event for event in events]
        return EventListResponse(events=merged, total=len(merged))

    def review_live_event(event_id: str, decision: EventStatus, actor: AuthenticatedUser, request: Request) -> TrafficEventResponse:
        events = read_scenario_events(selected_live_output_dir)
        source = next((item for item in events if item.event_id == event_id), None)
        if source is None:
            raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")
        if repository.get(event_id) is None:
            repository.add(TrafficEventIngest.model_validate(source.model_dump()))
        return apply_review(event_id, decision, actor, request)

    @application.post("/api/live-camera/events/{event_id}/verify", response_model=TrafficEventResponse, tags=["live camera"])
    def verify_live_event(event_id: str, request: Request, actor: AuthenticatedUser = Depends(require_roles("EMPLOYEE", "ADMIN"))) -> TrafficEventResponse:
        return review_live_event(event_id, EventStatus.VERIFIED, actor, request)

    @application.post("/api/live-camera/events/{event_id}/dismiss", response_model=TrafficEventResponse, tags=["live camera"])
    def dismiss_live_event(event_id: str, request: Request, actor: AuthenticatedUser = Depends(require_roles("EMPLOYEE", "ADMIN"))) -> TrafficEventResponse:
        return review_live_event(event_id, EventStatus.DISMISSED, actor, request)

    @application.get("/media/live-camera.mjpg", tags=["live camera"])
    def live_camera_stream() -> StreamingResponse:
        camera_id = read_camera_health(selected_live_output_dir).camera_id
        if read_live_snapshot(selected_live_output_dir, camera_id).metrics is None:
            raise HTTPException(status_code=503, detail="Waiting for fresh AI data.")
        return StreamingResponse(
            mjpeg_frames(selected_live_output_dir, is_current=lambda: read_live_snapshot(selected_live_output_dir, camera_id).metrics is not None),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/evidence/live/{filename}", response_class=FileResponse, tags=["live camera"])
    def live_camera_evidence(filename: str) -> FileResponse:
        path = resolve_evidence_path(selected_live_output_dir / "evidence", filename)
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @application.get(
        "/api/live-cameras",
        response_model=list[CameraHealthResponse],
        tags=["live camera"],
    )
    def live_cameras() -> list[CameraHealthResponse]:
        configured_ids = {
            camera_id.strip()
            for camera_id in os.getenv("CITYEYE_LIVE_CAMERA_IDS", "").split(",")
            if camera_id.strip()
        }
        directories = sorted(
            path for path in selected_live_output_dir.iterdir()
            if path.is_dir() and LIVE_CAMERA_ID_PATTERN.fullmatch(path.name)
            and (not configured_ids or path.name in configured_ids)
        ) if selected_live_output_dir.is_dir() else []
        return [read_camera_health(path) for path in directories]

    @application.get(
        "/api/live-cameras/{camera_id}/status",
        response_model=CameraHealthResponse,
        tags=["live camera"],
    )
    def selected_live_camera_status(camera_id: str) -> CameraHealthResponse:
        return read_camera_health(
            resolve_live_camera_directory(selected_live_output_dir, camera_id)
        )

    @application.get(
        "/api/live-cameras/{camera_id}/metrics",
        response_model=LiveMetricsSnapshot,
        tags=["live camera"],
    )
    def selected_live_camera_metrics(camera_id: str) -> LiveMetricsSnapshot:
        return read_live_snapshot(
            resolve_live_camera_directory(selected_live_output_dir, camera_id), camera_id
        )

    @application.get(
        "/api/analytics/traffic",
        response_model=OperationalAnalyticsResponse,
        tags=["analytics"],
    )
    def operational_traffic_analytics(
        camera_id: str = Query(min_length=1),
        start: float = Query(ge=0),
        end: float = Query(ge=0),
    ) -> OperationalAnalyticsResponse:
        if not LIVE_CAMERA_ID_PATTERN.fullmatch(camera_id):
            raise HTTPException(status_code=400, detail="Invalid live camera ID")
        if end <= start:
            raise HTTPException(status_code=400, detail="end must be after start")
        return query_operational_analytics(
            camera_id=camera_id,
            start=start,
            end=end,
            observations=traffic_observation_repository,
            events=repository,
            interval_seconds=observation_interval,
        )

    @application.get(
        "/api/live-cameras/{camera_id}/events",
        response_model=EventListResponse,
        tags=["live camera"],
    )
    def selected_live_camera_events(camera_id: str) -> EventListResponse:
        resolve_live_camera_directory(selected_live_output_dir, camera_id)
        incident_importer.sync_safely(camera_id)
        events = repository.page(source_type="LIVE_CAMERA", source_id=camera_id).events
        return EventListResponse(events=events, total=len(events))

    def review_selected_live_event(
        camera_id: str, event_id: str, decision: EventStatus,
        actor: AuthenticatedUser, request: Request,
    ) -> TrafficEventResponse:
        resolve_live_camera_directory(selected_live_output_dir, camera_id)
        incident_importer.sync_safely(camera_id)
        source = repository.get(event_id)
        if source is None or source.source_type != "LIVE_CAMERA" or source.source_id != camera_id:
            raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")
        return apply_review(event_id, decision, actor, request)

    @application.post(
        "/api/live-cameras/{camera_id}/events/{event_id}/verify",
        response_model=TrafficEventResponse,
        tags=["live camera"],
    )
    def verify_selected_live_event(camera_id: str, event_id: str, request: Request, actor: AuthenticatedUser = Depends(require_roles("EMPLOYEE", "ADMIN"))) -> TrafficEventResponse:
        return review_selected_live_event(camera_id, event_id, EventStatus.VERIFIED, actor, request)

    @application.post(
        "/api/live-cameras/{camera_id}/events/{event_id}/dismiss",
        response_model=TrafficEventResponse,
        tags=["live camera"],
    )
    def dismiss_selected_live_event(camera_id: str, event_id: str, request: Request, actor: AuthenticatedUser = Depends(require_roles("EMPLOYEE", "ADMIN"))) -> TrafficEventResponse:
        return review_selected_live_event(camera_id, event_id, EventStatus.DISMISSED, actor, request)

    @application.get("/media/live-cameras/{camera_id}.mjpg", tags=["live camera"])
    def selected_live_camera_stream(camera_id: str) -> StreamingResponse:
        directory = resolve_live_camera_directory(selected_live_output_dir, camera_id)
        snapshot = read_live_snapshot(directory, camera_id)
        health = snapshot.health
        if snapshot.metrics is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Camera {camera_id} is {health.state.lower()}." if health.state != "ONLINE" else "Waiting for fresh AI data.",
            )
        return StreamingResponse(
            mjpeg_frames(directory, is_current=lambda: read_live_snapshot(directory, camera_id).metrics is not None),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    @application.get(
        "/media/live-cameras/{camera_id}/preview.mjpg", tags=["live camera"]
    )
    def selected_live_camera_preview(camera_id: str) -> StreamingResponse:
        directory = resolve_live_camera_directory(selected_live_output_dir, camera_id)
        health = read_camera_health(directory)
        if health.state != "ONLINE":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Camera {camera_id} is {health.state.lower()}.",
            )
        def preview_is_current() -> bool:
            try:
                current = read_camera_health(directory)
            except ValueError:
                return False
            return (current.state == "ONLINE" and current.camera_id == camera_id
                    and current.generation == health.generation
                    and current.last_connected_at == health.last_connected_at)

        return StreamingResponse(
            mjpeg_frames(directory, filename="preview.jpg", is_current=preview_is_current),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    @application.get(
        "/evidence/live-cameras/{camera_id}/{filename}",
        response_class=FileResponse,
        tags=["live camera"],
    )
    def selected_live_camera_evidence(camera_id: str, filename: str) -> FileResponse:
        directory = resolve_live_camera_directory(selected_live_output_dir, camera_id)
        path = resolve_evidence_path(directory / "evidence", filename)
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

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

    def apply_review(
        event_id: str,
        decision: EventStatus,
        actor: AuthenticatedUser,
        request: Request,
    ) -> TrafficEventResponse:
        updated = repository.review_with_audit(event_id, decision, actor, request.state.request_id)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")
        return updated

    def review_scenario_event(
        scenario_id: str,
        event_id: str,
        decision: EventStatus,
        actor: AuthenticatedUser,
        request: Request,
    ) -> TrafficEventResponse:
        events = read_scenario_events(require_scenario(scenario_id))
        source = next((item for item in events if item.event_id == event_id), None)
        if source is None:
            raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")
        if repository.get(event_id) is None:
            repository.add(TrafficEventIngest.model_validate(source.model_dump()))
        return apply_review(event_id, decision, actor, request)

    @application.post("/api/scenarios/{scenario_id}/events/{event_id}/verify", response_model=TrafficEventResponse, tags=["scenarios"])
    def verify_scenario_event(
        scenario_id: str,
        event_id: str,
        request: Request,
        actor: AuthenticatedUser = Depends(require_roles("EMPLOYEE", "ADMIN")),
    ) -> TrafficEventResponse:
        return review_scenario_event(
            scenario_id, event_id, EventStatus.VERIFIED, actor, request
        )

    @application.post("/api/scenarios/{scenario_id}/events/{event_id}/dismiss", response_model=TrafficEventResponse, tags=["scenarios"])
    def dismiss_scenario_event(
        scenario_id: str,
        event_id: str,
        request: Request,
        actor: AuthenticatedUser = Depends(require_roles("EMPLOYEE", "ADMIN")),
    ) -> TrafficEventResponse:
        return review_scenario_event(
            scenario_id, event_id, EventStatus.DISMISSED, actor, request
        )

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
        _authorized: None = Depends(require_ingest_token),
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
        response_model=EventPageResponse,
        tags=["events"],
    )
    def list_events(
        event_repository: EventRepository = Depends(get_event_repository),
        limit: int = Query(default=100, ge=1, le=200),
        cursor: str | None = Query(default=None, max_length=2048),
        source_type: Literal["LIVE_CAMERA", "RECORDED_SCENARIO"] | None = None,
        source_id: str | None = Query(default=None, min_length=1, max_length=128),
    ) -> EventPageResponse:
        """Return bounded history; total counts the snapshot, not just this page."""
        try:
            return event_repository.page(limit=limit, cursor=cursor,
                                         source_type=source_type, source_id=source_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        request: Request,
        actor: AuthenticatedUser = Depends(require_roles("EMPLOYEE", "ADMIN")),
    ) -> TrafficEventResponse:
        """Apply a municipal human verification decision."""
        return apply_review(event_id, EventStatus.VERIFIED, actor, request)

    @application.post(
        "/api/events/{event_id}/dismiss",
        response_model=TrafficEventResponse,
        tags=["events"],
    )
    def dismiss_event(
        event_id: str,
        request: Request,
        actor: AuthenticatedUser = Depends(require_roles("EMPLOYEE", "ADMIN")),
    ) -> TrafficEventResponse:
        """Apply a municipal human dismissal decision."""
        return apply_review(event_id, EventStatus.DISMISSED, actor, request)

    @application.post(
        "/api/citizen-reports",
        response_model=CitizenReportResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["citizen reports"],
    )
    def create_citizen_report(
        report: CitizenReportCreate,
        actor: AuthenticatedUser = Depends(require_user),
        report_repository: CitizenReportRepository = Depends(
            get_citizen_report_repository
        ),
    ) -> CitizenReportResponse:
        """Store one citizen report with Backend-generated metadata."""
        return report_repository.add(
            report, authenticated_user_id=actor.user_id if auth_settings.required else None
        )

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
