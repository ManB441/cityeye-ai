# CITYEYE AI — MASTER PROJECT AUDIT

**As-of:** 2026-09-24T16:04:00.370837+00:00. **Target:** the actual working tree at `/Users/abcd/cityeye-ai`, based on commit `d9be07f` plus substantial existing local modifications. This is an observation/reporting audit, not a release or acceptance certificate.

**Verdict:** CityEye is a working, locally deployed traffic-video analysis and human-review MVP. Five recorded scenarios and a selected live DVR camera feed real model outputs into a React/FastAPI application. Detection, tracking, persistence, authentication and review have meaningful controlled evidence. Correct positive stopped-vehicle detection on Camera 3 is still **NOT VALIDATED**; Wrong Way and Road Blockage are disabled for that camera; the Citizen Map is a placeholder. The current backend test suite has one failure. The project is **not production-ready** on the available evidence.

## Audit boundaries and evidence hierarchy

Current code/configuration, safe executed tests, read-only database inspection and observed runtime take precedence over old documentation. Historical camera diagnostics are useful, but prove only their stated sample, date and conditions. A DB status of VERIFIED records a human action; it is not ground-truth proof of the detection algorithm.

Only the two requested audit files are intended repository changes. Tests used existing environments and temporary databases/output under `/tmp`; no dependencies were installed. No source/config changes, production login, event review, DB writes, worker restarts, video regeneration, commit or push were performed. The running service continued collecting data independently, so database totals naturally change. An existing authenticated browser session was unavailable; opening the app redirected to Login. Logging in would create a session and audit entries, so authenticated browser workflows were not exercised against the live DB.

**Observed evidence:** backend/frontend Docker services healthy in demo mode, authentication enabled, anonymous protected reads401; read-only SQLite quick_check OK with no FK violations; all14 deployed backend Python files match local hashes; served frontend asset names match the temporary current-source build. Camera3 published fresh changing status/JPEG observations; Camera5/7 artifact states were OFFLINE and are not selected in the running backend. The sampled Camera3 preview showed a visible road without a clearly visible vehicle; zero detections at that moment do not alone imply a fault. JSON contains the timestamped runtime snapshot, inventories, route catalog, tests, issues and priorities.

**Current test truth:** AI220 PASS; frontend59 PASS; backend247 PASS /1 FAIL; TypeScript and Vite build PASS. The backend failure is an exact timeline message-string mismatch, not a numeric-count failure in that fixture. These results do not validate municipal outcomes.

Evidence: [backend/tests/test_analysis_api.py:70](/Users/abcd/cityeye-ai/backend/tests/test_analysis_api.py:70), [backend/app/analysis.py:354](/Users/abcd/cityeye-ai/backend/app/analysis.py:354), [diagnostics/camera3-stopped-validation/validation-report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-stopped-validation/validation-report.md:1).

## Contents

1. Repository and reconstruction scope
2. Actual product
3. Vision versus current reality
4. Architecture
5. AI and event system
6. Cameras and recorded video
7. Incident lifecycle
8. API catalog
9. Database
10. Frontend
11. Authentication and security
12. Analytics definitions
13. Citizen system
14. Tests and verification limits
15. Performance and scaling
16. Known limitations and findings
17. Hackathon demo readiness
18. History and contradictions
19. Lessons
20. Product gaps
21. Evidence-driven priorities
22. What not to build yet
23. Business perspective
24. Master feature matrix
25. Project status dashboard
26. Terminology and integrity
27. CityEye in one page

## 1. Repository and reconstruction scope

```text
cityeye-ai/
  ai/
    process_video.py            model/tracker loop, output publication
    frame_source.py             files, RTSP, VLC adapters, freshness/reconnect
    trajectory.py              per-ID histories and movement state
    event_rules.py             stopped, wrong-way and congestion
    road_blockage.py            zone overlap/upstream-impact rule
    event_pipeline.py          rules → proposed event → JPEG/JSON
    calibration.py             camera-bound geometry safety gate
    evaluation.py              detector comparison/optional ground truth tooling
    config/                    live profile, ByteTrack, examples
      scenarios/               five LOCAL ignored scenario configurations
    sample_videos/             six local MP4 files (one candidate duplicate)
    scenario_outputs/          five registered outputs + unregistered stopped_vehicle_2
    live_output/               camera-3, camera-5, camera-7 + legacy root artifacts
    output/                    older experiments/default analysis output
    tests/                     existing AI regression suite
    yolov8n.pt                 local ignored production model
  backend/app/                 FastAPI, schemas, SQLite/auth/analytics/importer/backups
  backend/tests/               isolated API/storage/security/role/integration tests
  frontend/src/
    pages/                     Login, MunicipalDashboard, Cameras, Incidents,
                               Analytics, CitizenMap, Users
    components/                Incident, LiveMjpegImage, header/sidebar/login visual
    api/, hooks/, lib/         HTTP/session, source state, freshness checks
  scripts/                     smoke tests, preview profiling, live-camera control,
                               camera3 calibration tool, launchd files
  config/environments/         development/demo/production env examples
  diagnostics/                 camera quality/calibration/stopped evidence; partial frontend audit
  compose.yaml, compose.dev.yaml
  README.md, DOCKER.md, SECURE_ACCESS.md, LIVE_TRUTH.md,
  LIVE_INCIDENT_PIPELINE.md, CAMERA3_CALIBRATION.md, ROAD_BLOCKAGE.md
```

The JSON inventory lists inspected local source/artifact paths and sizes while excluding dependency trees, bytecode and secret contents. Local `.env` and `secrets/` exist; secret values were not used for access or included in deliverables. Package manifests/lockfile, virtual environments and `frontend/node_modules` are available, so no install was needed. There is no applicable repository AGENTS.md found by scoped search. The git worktree was already dirty before this audit; changes are not all represented in commit history.

Key reproducibility boundary: `.gitignore` excludes scenario configs, video inputs, AI outputs, weights, virtualenvs, DB files, frontend build and secrets. A fresh clone is therefore not equivalent to this functioning local workstation. launchd files use absolute `/Users/abcd/...` paths and configured DVR endpoints. The Docker backend DB resides in a named volume at `/data/cityeye.db`, not necessarily a DB file in this repo. Measured directory sizes: input videos213MiB, scenario outputs420MiB, live outputs97MiB, diagnostics286MiB (rounded `du -sh`; not growth rates).

Model: `ai/yolov8n.pt`,6,549,796 bytes, SHA256 `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`. No alternative detector was installed or run by this audit. Host versions: ultralytics 8.4.121, torch 2.13.0, torchvision 0.28.0, opencv-python 5.0.0.93, numpy 2.5.2, python-vlc 3.0.21203, lap 0.5.13. Host NumPy2.5.2 differs from runtime requirements pin2.4.6: a reproducibility issue, not proof of a runtime error.

Evidence: [.gitignore:1](/Users/abcd/cityeye-ai/.gitignore:1), [compose.yaml:1](/Users/abcd/cityeye-ai/compose.yaml:1), [ai/requirements.runtime.txt:1](/Users/abcd/cityeye-ai/ai/requirements.runtime.txt:1), [frontend/package.json:1](/Users/abcd/cityeye-ai/frontend/package.json:1), [scripts/launchd/com.cityeye.camera3.plist:1](/Users/abcd/cityeye-ai/scripts/launchd/com.cityeye.camera3.plist:1).

A local frozen evaluation dataset also exists at `ai/evaluation_dataset/frozen_p0_v1`:19 PNG references (3normal,3congestion,3rain,10stopped) plus a frame/source/time/dimension manifest. The manifest contains **no ground-truth bounding boxes** and the example ground-truth file has an empty frames array. Frozen stopped frames are1280×720, whereas the current input probes1920×1080; this further confirms a lineage/version boundary, not a new annotated accuracy result. No checked-in `.github` workflow directory was found; local tests passing does not establish automated CI gating. Evidence: [ai/evaluation_dataset/frozen_p0_v1/manifest.json:1](/Users/abcd/cityeye-ai/ai/evaluation_dataset/frozen_p0_v1/manifest.json:1), [ai/evaluation_ground_truth.example.json:1](/Users/abcd/cityeye-ai/ai/evaluation_ground_truth.example.json:1).

## 2. What CityEye actually does

CityEye turns traffic footage into model-generated observations and proposed incidents that a human can inspect. It aims to help a municipal traffic operator notice potentially relevant conditions without watching every camera continuously. The prospective buyer is a municipality/traffic authority; the operator/reviewer and administrator are actual implemented user roles, while a citizen role has only a limited report-list/map-foundation surface. Drivers, pedestrians and residents are intended beneficiaries, not verified paying users. No customer contract, municipal deployment or measured public benefit was verified.

```text
INPUTS
  DVR RTSP on selected host camera / local recorded MP4
  independent citizen report JSON
    ↓
CITYEYE
  host video worker + mounted artifacts + backend service
    ↓
PROCESSING
  decode → YOLO boxes/classes → ByteTrack IDs → movement/ROI/event rules
  citizen reports → separate nearby/time-compatible report clustering
    ↓
OUTPUTS
  annotated frames/video, sampled counts, traffic-state labels,
  proposed events with JPEG evidence, stored review state, history/analytics
    ↓
HUMAN ACTION
  select source → inspect event/evidence → Verify or Dismiss
  administrator manages access; no implemented municipal dispatch integration
```

Recorded viewing is playback of **precomputed results**, not a browser-triggered AI analysis job. Citizen reports do not enter YOLO and are not automatically corroborated with camera incidents. An alert currently means a visible proposal/card, not a verified SMS/email/push notification or an automatic enforcement action.

Evidence: [ai/process_video.py:631](/Users/abcd/cityeye-ai/ai/process_video.py:631), [backend/app/main.py:910](/Users/abcd/cityeye-ai/backend/app/main.py:910), [frontend/src/pages/MunicipalDashboard.tsx:784](/Users/abcd/cityeye-ai/frontend/src/pages/MunicipalDashboard.tsx:784), [frontend/src/pages/CitizenMapPage.tsx:81](/Users/abcd/cityeye-ai/frontend/src/pages/CitizenMapPage.tsx:81), [frontend/src/components/Incident.tsx:1](/Users/abcd/cityeye-ai/frontend/src/components/Incident.tsx:1).

## 3. Vision versus current reality

### A. CITYEYE VISION

Repository language describes municipal traffic intelligence using existing CCTV, detection/tracking, reviewable incidents, traffic history and citizen geographic information. That is a direction of travel, not proof of citywide operation, dispatch, forecasting, LPR or a validated public map.

### B. CITYEYE CURRENT REALITY

The following table distinguishes implemented mechanics from validated outcomes. HIGH confidence describes confidence in this audit finding, **not AI accuracy**. Controlled tests are detailed in section14; demo/production qualification is consolidated in section24.

| Feature | Status | Evidence | What actually works | Missing / limitation | Audit confidence |
| --- | --- | --- | --- | --- | --- |
| Vehicle detection/classification | IMPLEMENTED BUT PARTIAL | [ai/process_video.py:897](/Users/abcd/cityeye-ai/ai/process_video.py:897); [diagnostics/camera3-calibration-day/calibration-report.md:32](/Users/abcd/cityeye-ai/diagnostics/camera3-calibration-day/calibration-report.md:32) | COCO car/bus/truck/motorcycle boxes and per-frame counts | No labeled municipal precision/recall; misses and classification errors remain | HIGH |
| Person and bicycle detection | IMPLEMENTED BUT PARTIAL | [ai/process_video.py:984](/Users/abcd/cityeye-ai/ai/process_video.py:984) | Boxes/counts; bottom-center road membership; possible-rider heuristic | No independent person-in-road incident; no real accuracy study | HIGH |
| ByteTrack identities | IMPLEMENTED BUT PARTIAL | [ai/config/bytetrack_cityeye.yaml:1](/Users/abcd/cityeye-ai/ai/config/bytetrack_cityeye.yaml:1); [ai/process_video.py:853](/Users/abcd/cityeye-ai/ai/process_video.py:853) | Persistent IDs within source generation | No cross-camera identity; no ID-switch benchmark | HIGH |
| Movement/trajectory state | IMPLEMENTED BUT NOT VALIDATED | [ai/trajectory.py:31](/Users/abcd/cityeye-ai/ai/trajectory.py:31) | Median normalized movement, moving/stationary state, timers | Image-space movement is not road speed; physical stop causality incomplete | HIGH |
| Recorded video integration | IMPLEMENTED | [backend/app/scenarios.py:1](/Users/abcd/cityeye-ai/backend/app/scenarios.py:1); [frontend/src/pages/MunicipalDashboard.tsx:784](/Users/abcd/cityeye-ai/frontend/src/pages/MunicipalDashboard.tsx:784) | Five registered scenarios; annotated MP4/CSV/events/timeline | Precomputed playback; no upload/job management UI; provenance manifests missing | HIGH |
| Maydan Palestine | IMPLEMENTED BUT PARTIAL | [ai/config/scenarios/maydan_palestine.json:1](/Users/abcd/cityeye-ai/ai/config/scenarios/maydan_palestine.json:1); [backend/app/scenarios.py:38](/Users/abcd/cityeye-ai/backend/app/scenarios.py:38) | 1024×576, 312.15s, 6243-frame H.264 annotated output; detection IDs visible | Coordinates 0,0; broad ROI/global vector unvalidated; zero incident artifacts | HIGH |
| RTSP/DVR ingestion | IMPLEMENTED BUT PARTIAL | [ai/frame_source.py:644](/Users/abcd/cityeye-ai/ai/frame_source.py:644); [ai/frame_source.py:827](/Users/abcd/cityeye-ai/ai/frame_source.py:827) | Host VLC remux/OpenCV decode, latest-frame capture and reconnect | Single selected camera evidence; repeated reconnects; long outage reliability unmeasured | HIGH |
| JPEG/MJPEG preview and AI view | IMPLEMENTED BUT PARTIAL | [ai/process_video.py:400](/Users/abcd/cityeye-ai/ai/process_video.py:400); [backend/app/main.py:838](/Users/abcd/cityeye-ai/backend/app/main.py:838); [frontend/src/components/LiveMjpegImage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/components/LiveMjpegImage.tsx:1) | Independent raw preview and annotated AI publication | Raw stream lacks in-stream freshness callback; UI retry budget not reset on load | HIGH |
| Live freshness/generation truth | IMPLEMENTED | [backend/app/live_camera.py:74](/Users/abcd/cityeye-ai/backend/app/live_camera.py:74); [frontend/src/lib/liveTruth.ts:1](/Users/abcd/cityeye-ai/frontend/src/lib/liveTruth.ts:1) | Health heartbeat, source/generation/age validation, frontend local expiry | Frame/JSON publications not one transaction; not a network-latency guarantee | HIGH |
| Camera 3 road/stopped calibration | IMPLEMENTED BUT PARTIAL | [ai/config/live_camera.json:78](/Users/abcd/cityeye-ai/ai/config/live_camera.json:78); [ai/calibration.py:1](/Users/abcd/cityeye-ai/ai/calibration.py:1) | 944×1080 camera-specific polygons; identity/resolution/shape safety checks | Daylight-only manual night guard; incomplete roadway coverage; positive event acceptance missing | HIGH |
| Stopped Vehicle event | IMPLEMENTED BUT NOT VALIDATED | [ai/event_rules.py:284](/Users/abcd/cityeye-ai/ai/event_rules.py:284); [diagnostics/camera3-stopped-validation/validation-report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-stopped-validation/validation-report.md:1) | Prior sustained motion, stationary timer, one event per episode, rearm | No genuine Camera 3 positive; current demo event is documented pre-fix false proposal | HIGH |
| Wrong Way event | IMPLEMENTED BUT NOT VALIDATED | [ai/event_rules.py:154](/Users/abcd/cityeye-ai/ai/event_rules.py:154); [ai/config/live_camera.json:88](/Users/abcd/cityeye-ai/ai/config/live_camera.json:88) | Trajectory opposition with zone/displacement/persistence checks | Camera 3 direction disabled; no legally direction-labeled positive clip | HIGH |
| Congestion event/state | IMPLEMENTED BUT PARTIAL | [ai/event_rules.py:455](/Users/abcd/cityeye-ai/ai/event_rules.py:455); [ai/scenario_outputs/congestion/events.json:1](/Users/abcd/cityeye-ai/ai/scenario_outputs/congestion/events.json:1) | Count/density/spacing/persistence rule; recorded event at 5s | Live sensitivity not calibrated by positives; dense moving traffic can satisfy high-count branch | HIGH |
| Road Blockage event | IMPLEMENTED BUT NOT VALIDATED | [ai/road_blockage.py:70](/Users/abcd/cityeye-ai/ai/road_blockage.py:70); [ROAD_BLOCKAGE.md:1](/Users/abcd/cityeye-ai/ROAD_BLOCKAGE.md:1) | Stationary bbox overlap with optional upstream impact; evidence/details | Camera 3 deliberately disabled; real blocked-lane positive missing | HIGH |
| Person-in-road incident | NOT IMPLEMENTED | [backend/app/schemas.py:12](/Users/abcd/cityeye-ai/backend/app/schemas.py:12); [ai/process_video.py:984](/Users/abcd/cityeye-ai/ai/process_video.py:984) | Road membership flags exist | No event enum/rule/persistence lifecycle for this incident | HIGH |
| Evidence generation/serving | IMPLEMENTED BUT PARTIAL | [ai/event_pipeline.py:364](/Users/abcd/cityeye-ai/ai/event_pipeline.py:364); [backend/app/live_incidents.py:1](/Users/abcd/cityeye-ai/backend/app/live_incidents.py:1); [backend/app/main.py:166](/Users/abcd/cityeye-ai/backend/app/main.py:166) | Real annotated JPEG, safe serving paths, live import checks completeness | Files outside DB backups; recorded names can be overwritten by reruns | HIGH |
| Live incident persistence/replay | IMPLEMENTED | [backend/app/live_incidents.py:1](/Users/abcd/cityeye-ai/backend/app/live_incidents.py:1); [backend/tests/test_live_incidents.py:1](/Users/abcd/cityeye-ai/backend/tests/test_live_incidents.py:1) | Atomic event JSON, periodic importer, UUID idempotency, source-bound rows | Physical episode dedupe across worker restarts not guaranteed; unbounded history | HIGH |
| Recorded incident persistence | IMPLEMENTED BUT PARTIAL | [backend/app/main.py:918](/Users/abcd/cityeye-ai/backend/app/main.py:918); [backend/app/main.py:937](/Users/abcd/cityeye-ai/backend/app/main.py:937) | Scenario file listing merges DB reviews; review lazily imports | Unreviewed artifacts not automatically DB-persisted; source identity may be null | HIGH |
| Human review/audit | IMPLEMENTED BUT PARTIAL | [backend/app/database.py:279](/Users/abcd/cityeye-ai/backend/app/database.py:279); [frontend/src/pages/MunicipalDashboard.tsx:490](/Users/abcd/cityeye-ai/frontend/src/pages/MunicipalDashboard.tsx:490) | Verify/Dismiss and audit committed together; role checks | Command Center failure handling can misstate local review; no assignment/dispatch lifecycle | HIGH |
| Operational analytics | IMPLEMENTED BUT PARTIAL | [backend/app/operational_analytics.py:1](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:1); [frontend/src/pages/AnalyticsPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/AnalyticsPage.tsx:1) | SQLite one-minute observations, range/bucket/count/composition/history | Not throughput; sparse samples; chart gap distortion; camera-name incident join | HIGH |
| Citizen report API/storage/clustering | DEMO ONLY | [backend/app/database.py:367](/Users/abcd/cityeye-ai/backend/app/database.py:367); [backend/app/main.py:1068](/Users/abcd/cityeye-ai/backend/app/main.py:1068) | Categories, coordinates, five-ID nearby/time-window confirmation | Client-supplied demo identity; public POST; no abuse control or AI corroboration | HIGH |
| Citizen geographic map | PLACEHOLDER | [frontend/src/pages/CitizenMapPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/CitizenMapPage.tsx:1) | Citizen-only route displays report list and explicit unavailable map | No plotted geography/provider/submission form | HIGH |
| Authentication and three-role RBAC | IMPLEMENTED | [backend/app/auth.py:1](/Users/abcd/cityeye-ai/backend/app/auth.py:1); [backend/tests/test_role_access.py:1](/Users/abcd/cityeye-ai/backend/tests/test_role_access.py:1) | Hashed passwords/sessions, Admin/Employee/Citizen separation, revocation | No password reset/MFA/SSO/lockout; demo HTTP; Employee cannot manage accounts at all | HIGH |
| User access administration | IMPLEMENTED | [frontend/src/pages/UsersPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/UsersPage.tsx:1); [backend/app/auth.py:209](/Users/abcd/cityeye-ai/backend/app/auth.py:209) | Admin creates, changes roles, enables/disables; final-admin guard | No billing/subscription product or self-service recovery | HIGH |
| Container deployment and host worker | IMPLEMENTED BUT PARTIAL | [compose.yaml:1](/Users/abcd/cityeye-ai/compose.yaml:1); [scripts/launchd/com.cityeye.camera3.plist:1](/Users/abcd/cityeye-ai/scripts/launchd/com.cityeye.camera3.plist:1) | Healthy backend/frontend; launchd host Camera 3 artifacts | Not portable turnkey install; local absolute paths and ignored assets; no HTTPS termination | HIGH |
| Backups/recovery | IMPLEMENTED BUT PARTIAL | [backend/app/backups.py:1](/Users/abcd/cityeye-ai/backend/app/backups.py:1); [compose.yaml:68](/Users/abcd/cityeye-ai/compose.yaml:68) | SQLite backup/checksum/retention/restore utilities and tests | Backup service not running; backup volume absent; evidence/config not backed up | HIGH |
| Prediction / forecasting | NOT IMPLEMENTED | [frontend/src/pages/AnalyticsPage.tsx:106](/Users/abcd/cityeye-ai/frontend/src/pages/AnalyticsPage.tsx:106) | Unavailable UI label | No model, forecast API, training or forecast validation | HIGH |
| LPR/ANPR / real speed / cross-camera re-ID | NOT IMPLEMENTED | [ai/process_video.py:59](/Users/abcd/cityeye-ai/ai/process_video.py:59); [ai/trajectory.py:1](/Users/abcd/cityeye-ai/ai/trajectory.py:1) | None in audited runtime pipeline | Suitable data/calibration/models/validation absent | HIGH |
| External alerts and municipal dispatch | NOT IMPLEMENTED | [backend/app/main.py:1](/Users/abcd/cityeye-ai/backend/app/main.py:1); [frontend/src/components/Incident.tsx:1](/Users/abcd/cityeye-ai/frontend/src/components/Incident.tsx:1) | On-screen proposal visibility only | No verified SMS/email/push/dispatch/integration pipeline | HIGH |

## 4. Technical architecture and communication

| Layer | Technology | Why it exists | Communication | Evidence |
| --- | --- | --- | --- | --- |
| Sources | DVR RTSP; local MP4; citizen JSON HTTP | Accept existing camera footage or precomputed demo input and independent human reports | Private RTSP→host worker; local video→offline worker; POST→API | [ai/frame_source.py:1](/Users/abcd/cityeye-ai/ai/frame_source.py:1); [backend/app/main.py:1068](/Users/abcd/cityeye-ai/backend/app/main.py:1068) |
| Decode/capture | OpenCV/FFmpeg; macOS headless VLC MPEG-TS remux; optional native VLC callbacks elsewhere | Normalize legacy streams and keep latest frame without unbounded inference backlog | FramePacket(frame,index,timestamp,generation) | [ai/frame_source.py:44](/Users/abcd/cityeye-ai/ai/frame_source.py:44); [ai/frame_source.py:644](/Users/abcd/cityeye-ai/ai/frame_source.py:644) |
| Detection/tracking | Ultralytics YOLOv8n COCO, PyTorch, ByteTrack/lap | Produce accepted road-user classes/boxes/IDs | Full decoded BGR array→normal model preprocessing→track outputs | [ai/process_video.py:897](/Users/abcd/cityeye-ai/ai/process_video.py:897) |
| State/rules | Python trajectory manager, calibration resolver, spatial/temporal rules | Convert noisy positions into bounded histories and proposed events | Centers/boxes/time→state→ROI rules→TrafficEvent UUID | [ai/trajectory.py:1](/Users/abcd/cityeye-ai/ai/trajectory.py:1); [ai/event_pipeline.py:1](/Users/abcd/cityeye-ai/ai/event_pipeline.py:1) |
| AI delivery artifacts | JPG, MP4, CSV, atomic JSON files | Publish preview/evidence/metrics and replayable event list | Host-mounted filesystem→backend read-only volumes | [ai/process_video.py:344](/Users/abcd/cityeye-ai/ai/process_video.py:344); [compose.yaml:1](/Users/abcd/cityeye-ai/compose.yaml:1) |
| Backend | FastAPI/Uvicorn, Pydantic, SQLite | Validate, persist, protect, aggregate and expose the product | Importer every2s; observation collector every5s storing max1/min; JSON API/MJPEG/files | [backend/app/main.py:259](/Users/abcd/cityeye-ai/backend/app/main.py:259); [backend/app/operational_analytics.py:1](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:1) |
| Frontend | React18/TypeScript, React Router6, Vite5; nginx static/proxy | Select sources, show current/replayed observations, review proposals, inspect analytics and accounts | Same-origin HTTP polling, MP4/MJPEG, session cookie | [frontend/package.json:1](/Users/abcd/cityeye-ai/frontend/package.json:1); [frontend/src/App.tsx:1](/Users/abcd/cityeye-ai/frontend/src/App.tsx:1); [frontend/nginx.conf:1](/Users/abcd/cityeye-ai/frontend/nginx.conf:1) |
| Operations | Docker Compose backend/frontend; host launchd AI; optional backup service | Keep processes running and persist local state | Docker named DB volume; host AI bind mounts; launchd absolute paths | [compose.yaml:1](/Users/abcd/cityeye-ai/compose.yaml:1); [scripts/launchd/com.cityeye.camera3.plist:1](/Users/abcd/cityeye-ai/scripts/launchd/com.cityeye.camera3.plist:1) |

Deployment detail: backend and AI Dockerfiles use pinned Python3.11-slim base digest; frontend builds with Node20 and serves nginx1.27. Backend requirements pin FastAPI0.115.14/Uvicorn0.52.4/httpx0.28.1; local backend Pydantic is2.13.4 and its transitive resolution is not a complete lockfile. The AI image specifies CPU-only PyTorch/TorchVision before remaining runtime requirements. `ai/.dockerignore` excludes models/videos/generated data, and compose's optional live-ai service uses a template config by default, so building that image is not equivalent to the configured host Camera3 deployment. Development compose uses source mounts, uvicorn reload and a Vite development target; it is not the observed production-style nginx container. Runtime logs are structured JSON with request IDs, status and duration fields plus common secret redaction; Docker logs have size/file limits, but no centralized alerting/host worker log retention was established. Evidence: [ai/Dockerfile:1](/Users/abcd/cityeye-ai/ai/Dockerfile:1), [backend/Dockerfile:1](/Users/abcd/cityeye-ai/backend/Dockerfile:1), [frontend/Dockerfile:1](/Users/abcd/cityeye-ai/frontend/Dockerfile:1), [compose.dev.yaml:1](/Users/abcd/cityeye-ai/compose.dev.yaml:1), [backend/app/observability.py:1](/Users/abcd/cityeye-ai/backend/app/observability.py:1).

The browser never connects directly to the DVR. On this macOS host, VLC remuxes the legacy RTSP stream to localhost MPEG-TS without transcoding; OpenCV decodes it into BGR frames. The alternative direct libVLC RV32/I420 callbacks still exist, but are not the default macOS capture path now. A background capture thread owns health and the newest frame; slower AI inference reads the latest packet, intentionally skipping intervening frames. Preview publication runs separately, so preview cadence can exceed inference cadence.

The host worker writes files, while Docker's backend mounts the output directories read-only. The backend writes its own SQLite named volume. It imports live event files at startup and every2s; a separate collector polls every5s and inserts at most one valid observation per camera per60s interval. REST JSON and MJPEG/MP4/evidence responses go through nginx, which also serves the built React app and SPA route fallback. There is no queue broker, independent inference service API, tenant store, distributed storage or fleet scheduler in the audited deployment.

Both the default/legacy single-output endpoints and per-camera/scenario endpoints exist. The current UI primarily uses the latter. Per-camera status is independently available from metrics: a running source can be ONLINE while AI is stale or missing. API readiness only requires the DB health check to pass; optional AI artifacts and camera quality do not make the service unready.

Evidence: [ai/frame_source.py:876](/Users/abcd/cityeye-ai/ai/frame_source.py:876), [backend/app/main.py:268](/Users/abcd/cityeye-ai/backend/app/main.py:268), [backend/app/main.py:644](/Users/abcd/cityeye-ai/backend/app/main.py:644), [frontend/nginx.conf:1](/Users/abcd/cityeye-ai/frontend/nginx.conf:1).

## 5. AI system and event audit

### Model, thresholds, preprocessing and identity

Current configured detector is COCO-pretrained **YOLOv8n**, loaded through Ultralytics8.4.121/PyTorch2.13.0; no custom municipal training evidence was found. Supported COCO IDs are0 person,1 bicycle,2 car,3 motorcycle,5 bus,7 truck. Live Camera3 uses full decoded944×1080 input, image-size argument960 and IoU0.7. Ultralytics performs its own resize/letterbox/RGB normalization. Inference receives the raw decoded image before drawing annotations; neither the annotated JPEG nor browser preview is the production AI input.

Vehicle confidence is .22 for Camera3, person/bicycle floors .22. The `model.track` threshold is the minimum of configured class thresholds, followed by class-specific filtering. Recorded normal/congestion vehicle threshold .25/imgsz1280; Maydan .25/960; rain/stopped .40/default960; person/bicycle floor defaults .22. This means a scenario's vehicle threshold is not always the actual raw inference floor. Congestion separately rejects detections below its own default .30. ByteTrack high/new=.22, low=.10, buffer30, match=.80, fuse_score=true. A .10 tracker setting does not prove .10 detector boxes arrive when model inference is already filtered at .22.

Vehicle class stabilization uses a bounded7-observation history. Trajectory history is30 observations; per-track image center displacement/time produces pixel speed, then ROI diagonal normalization and a median of5 recent normalized speeds. Camera3 movement classification needs2 confirmations and moving hysteresis2×stationary threshold. A gap>1s clears speed/stationary accumulation; stale trajectory records expire after2s. Some movement flags remain sticky within a surviving TrackState; the stopped rule separately qualifies sustained prior motion. New stream generations/resolution changes reset tracker/trajectory/rule temporal state. IDs are local track labels, not vehicle identity across reconnects or cameras. No calibrated km/h output exists.

A same-resolution camera reposition is not automatically detected by the calibration validator. The current calibration mechanism is **opt-in**: Camera3 has a profile, while Camera5/7 would fall back to legacy shared geometry if activated without a profile. Safety checks include matching camera identity, frame dimensions, absolute-pixel bounds, duplicate/degenerate/self-intersecting polygons, containment and nonzero in-zone direction. DAYLIGHT_ONLY is documentation metadata, not an automatic runtime light-condition gate.

Evidence: [ai/process_video.py:631](/Users/abcd/cityeye-ai/ai/process_video.py:631), [ai/process_video.py:887](/Users/abcd/cityeye-ai/ai/process_video.py:887), [ai/config/bytetrack_cityeye.yaml:1](/Users/abcd/cityeye-ai/ai/config/bytetrack_cityeye.yaml:1), [ai/trajectory.py:31](/Users/abcd/cityeye-ai/ai/trajectory.py:31), [ai/calibration.py:98](/Users/abcd/cityeye-ai/ai/calibration.py:98), [ai/config/live_camera.json:1](/Users/abcd/cityeye-ai/ai/config/live_camera.json:1).

### STOPPED_VEHICLE


| Aspect | Finding |
| --- | --- |
| Implementation | IMPLEMENTED, positive acceptance NOT VALIDATED |
| Trigger | Eligible sustained prior motion above release threshold for rearm interval; center inside stopped ROI, contiguous min points, low smoothed + instantaneous movement, stationary duration threshold |
| Calibration | Camera-specific road/stopped ROI and scale |
| Live Settings | 8s; normalized stop0.01; release0.025; rearm1s; min5 points; prior motion true |
| Dedup | active_track_ids suppress one stop episode |
| Rearm | Sustained movement inside ROI for1s; generation resets temporal state |
| Evidence | Annotated JPG then atomic events.json; structured speed/duration/track details |
| Persistence | Live importer→events_v2; recorded lazy review/explicit ingest |
| Ui | Command Center/Incidents |
| Tests | test_stopped_vehicle.py, test_event_pipeline.py pass |
| Real Validation | Sep18 300s observer: moving YES, natural stop NO; stored false recorded proposal dismissed |
| Limitations | ROI membership checked at evaluation, stationary timer maintained by global track; timer is not guaranteed entirely spent inside stopped ROI |

Evidence: [ai/event_rules.py:284](/Users/abcd/cityeye-ai/ai/event_rules.py:284); [ai/trajectory.py:1](/Users/abcd/cityeye-ai/ai/trajectory.py:1); [diagnostics/camera3-stopped-validation/validation-report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-stopped-validation/validation-report.md:1).

### WRONG_WAY


| Aspect | Finding |
| --- | --- |
| Implementation | IMPLEMENTED; Camera3 DISABLED |
| Trigger | Track-center in zone; contiguous in-zone displacement opposite configured vector, score=max(0,-cosine), min displacement/points/repeated evaluations |
| Calibration | Verified legally allowed direction per zone |
| Live Settings | Configured0.8 score,0.04 diagonal displacement,6 points,4 opposite observations; inactive on Camera3 |
| Dedup | One emitted ID per rule/track |
| Rearm | No same-ID rearm; new worker/generation resets state |
| Evidence | JPG and vector/displacement details |
| Persistence | Shared event pipeline |
| Ui | Shared incident review |
| Tests | test_wrong_way.py + pipeline pass |
| Real Validation | NOT VALIDATED; old VERIFIED row predates valid direction and cannot be used as proof |
| Limitations | Rule confidence is geometric opposition, not detector probability or calibrated incident likelihood |

Evidence: [ai/event_rules.py:154](/Users/abcd/cityeye-ai/ai/event_rules.py:154); [ai/calibration.py:141](/Users/abcd/cityeye-ai/ai/calibration.py:141).

### CONGESTION


| Aspect | Finding |
| --- | --- |
| Implementation | IMPLEMENTED; positive live event NOT VALIDATED |
| Trigger | ROI-center vehicles ≥16 plus density≥.04 OR spacing≤.12; alternative ≥12 with density+spacing+movement≤.12; persists5s; release grace.75s |
| Calibration | Road ROI, scale and camera-specific traffic thresholds |
| Live Settings | Additional rule detection confidence floor .30; perspective weight .5; movement unknown can pass movement_ok |
| Dedup | event_emitted while congestion sustained |
| Rearm | Condition clears beyond grace or evaluation gap>1s resets episode |
| Evidence | JPG plus count/duration/density state |
| Persistence | Shared live/recorded delivery |
| Ui | Traffic state + incidents + sampled analytics |
| Tests | test_congestion.py + pipeline + analytics pass |
| Real Validation | Existing recorded congestion artifact5s; Camera3 positive NOT VALIDATED |
| Limitations | High-count branch need not be slow; image density not physical road occupancy; NORMAL not proof road clear |

Evidence: [ai/event_rules.py:525](/Users/abcd/cityeye-ai/ai/event_rules.py:525); [ai/event_pipeline.py:152](/Users/abcd/cityeye-ai/ai/event_pipeline.py:152).

### ROAD_BLOCKAGE


| Aspect | Finding |
| --- | --- |
| Implementation | IMPLEMENTED controlled rule; Camera3 DISABLED |
| Trigger | Tracked stationary object overlaps configured zone >=.35 bbox fraction; >=.60 strengthens score; optional2 slow upstream vehicles for1s strengthens impact |
| Calibration | Blockage zone, nonzero direction, perspective/overlap/upstream thresholds |
| Live Settings | No approved Camera3 blockage zones; calibration always CONFIGURATION_REQUIRED |
| Dedup | emitted_track_ids episode set |
| Rearm | Motion above pixel threshold or missing track beyond gap clears |
| Evidence | Zone polygon + blocking box JPEG; structured obstruction/upstream metrics |
| Persistence | Shared event contract accepts structured required details |
| Ui | Dedicated measured detail fields |
| Tests | test_road_blockage.py + event/API tests pass |
| Real Validation | NOT VERIFIED; ROAD_BLOCKAGE.md explicitly requires real footage |
| Limitations | No required prior-motion qualification like stopped rule; impact is optional, not mandatory; physical lane blockage unproven |

Evidence: [ai/road_blockage.py:70](/Users/abcd/cityeye-ai/ai/road_blockage.py:70); [ai/calibration.py:156](/Users/abcd/cityeye-ai/ai/calibration.py:156).

### PERSON_IN_ROAD / BICYCLE_IN_ROAD


| Aspect | Finding |
| --- | --- |
| Implementation | MEMBERSHIP METRIC ONLY; event NOT IMPLEMENTED |
| Trigger | Detection bbox bottom-center inside road polygon |
| Calibration | Road polygon |
| Live Settings | Class floor.22; no incident temporal settings |
| Dedup | Not applicable |
| Rearm | Not applicable |
| Evidence | Per-frame flags/annotated boxes; no separate incident image lifecycle |
| Persistence | Recorded CSV/timeline counts; aggregate live people/bicycles |
| Ui | Road-user counts, not reviewable person-in-road incidents |
| Tests | process_video/analysis tests |
| Real Validation | Membership accuracy NOT VERIFIED |
| Limitations | Possible-rider overlap heuristic is not semantic pedestrian hazard reasoning |

Evidence: [ai/process_video.py:984](/Users/abcd/cityeye-ai/ai/process_video.py:984); [backend/app/schemas.py:12](/Users/abcd/cityeye-ai/backend/app/schemas.py:12).

### Confidence and validation boundaries

Wrong-way confidence is directional opposition; stopped confidence combines duration and movement; congestion confidence is count-based; blockage combines overlap/impact terms. These are hand-designed rule scores, **not calibrated probabilities of an incident being true**. Detector confidence and rule confidence must not be mixed.

The Sep18 stopped investigation found that the existing broken-car clip was already stationary. Short bounding-box jitter set prior movement and produced a false proposal. The current StoppedVehicleRule adds sustained prior-motion qualification using the existing rearm interval. The documented post-fix replay emitted zero events: a successful **negative regression**, a failed **positive acceptance scenario**. That correction remains in source and its existing regression tests pass now. This audit did not rerun the model or fabricate a positive event.

The road-blockage rule is not generic object/debris detection: it uses tracked vehicles and box/zone overlap. Upstream impact increases confidence but is not mandatory for a proposal. It does not inherit the stopped rule's sustained prior-motion check. The calibration resolver deliberately disables it for Camera3.

There is no verified labeled precision/recall/F1, ID-switch score, event false-alarm rate, municipal reviewer acceptance study or operational response-time improvement. `evaluation.py` can compute detection matching with provided annotations, but the historical evaluation report states annotations were absent. Its higher box counts with alternate model variants are not evidence of higher accuracy.

Evidence: [diagnostics/camera3-stopped-validation/validation-report.md:34](/Users/abcd/cityeye-ai/diagnostics/camera3-stopped-validation/validation-report.md:34), [ai/event_rules.py:417](/Users/abcd/cityeye-ai/ai/event_rules.py:417), [ai/road_blockage.py:175](/Users/abcd/cityeye-ai/ai/road_blockage.py:175), [ai/EVALUATION_REPORT.md:115](/Users/abcd/cityeye-ai/ai/EVALUATION_REPORT.md:115), [ai/evaluation.py:1](/Users/abcd/cityeye-ai/ai/evaluation.py:1).

## 6. Cameras, source quality and recorded scenarios

### Current camera status

Status below is a dated observation, not a promise of current availability when read later. Source addresses are intentionally omitted.

| ID | Source/type | Resolution | Observed state | Detection/tracking/event evidence | Calibration and recommendation |
| --- | --- | --- | --- | --- | --- |
| camera-3 | DVR RTSP, host launchd/VLC bridge | 944×1080 | ONLINE; snapshot generation116, reconnect attempts851; fresh artifacts | Daylight detection/tracking proven on limited Sep18 samples; present sampled scene had0vehicles; only old wrong-way live DB incident | Road/stopped/congestion READY; wrong-way/road-blockage disabled; daylight only, manual night-disable |
| camera-5 | DVR RTSP config/old output | Current resolution NOT VERIFIED | OFFLINE artifact; excluded by CITYEYE_LIVE_CAMERA_IDS | Old capture counters only; correct detections/tracks/events NOT VERIFIED | No approved per-camera profile found; keep disabled until calibrated and validated |
| camera-7 | DVR RTSP config/old output | Current resolution NOT VERIFIED | OFFLINE artifact; excluded by CITYEYE_LIVE_CAMERA_IDS | Old capture counters only; correct detections/tracks/events NOT VERIFIED | No approved per-camera profile found; keep disabled until calibrated and validated |
| municipal-pilot-01 / legacy root | Template identity/root-output compatibility | NOT VERIFIED | Not the selected current worker identity | Do not count as another deployed camera | Actual Camera3 CLI overrides generic camera_id/name |

### What has been proven about Camera3

The archived Sep18 diagnostic contains20 consecutive decoded frames over1.561s,944×1080 and0% exact duplicates. Three cars were found in each frame, confidence .254–.883. A diagnostic isolated replay intercepted YOLO input arrays and found exact equality with decoded arrays; its ByteTrack instrumentation received/returned all three detections. Concurrent live JPEGs showed the same scene. This is strong evidence against major software degradation **in that daytime sample**, not an exact production-input tap or broad recall benchmark. It also does not prove vehicle motion merely because pixels change.

Historical interior sharpness/contrast differed greatly between night and day: Laplacian variance .882 versus78.18 and grayscale standard deviation17.69 versus39.84, as documented for those particular samples. The severe old night veil is evidence of an input/condition problem, but its precise lens/IR/exposure/DVR mechanism remains **UNDETERMINED**. Daylight replay JPEG quality75 produced about40.53dB PSNR. These are archived measurements, not fresh measurements made by this audit.

Daylight calibration observation covered355 samples/~180s and showed ROI exclusion/inclusion and persistent moving IDs. Its own report notes a visibly present foreground vehicle without a box. The stopped validation observed300s through an independent preview-based observer plus passive worker outputs: moving traffic was observed, but no natural eligible movement→stop episode occurred. Observer track IDs/timers are not identical to internal production IDs/timers. This audit's current preview was changing and visually readable as a road, but did not establish a positive incident.

The live source uses timestamps after successful reads; DVR on-screen clock is not guaranteed synchronized to host wall time. Camera3's current repeated reconnect counter is evidence of reconnect activity, not a measured failure rate because start time/exposure denominator was not established. No outage was induced during this audit.

Evidence: [diagnostics/camera3-diagnostic/report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-diagnostic/report.md:1), [diagnostics/camera3-calibration-day/calibration-report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-calibration-day/calibration-report.md:1), [diagnostics/camera3-stopped-validation/validation-report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-stopped-validation/validation-report.md:1), [ai/frame_source.py:203](/Users/abcd/cityeye-ai/ai/frame_source.py:203).

### Frame pipeline controls and remaining gaps

RTSP supports OPENCV/VLC/AUTO adapters and VIDEO_FILE supports OpenCV file reads. Capture reconnect backoff is2→16s; configured stale read limit5s. Visual freshness uses downsampled frame differences, threshold.08,15s and30 similar frames after arming from3 changes. Source noise or OSD can still differ without actual vehicle motion. Stream generation increments on a successful connection's first decoded frame, with temporal state reset. Host preview requests12FPS and inference caps5FPS, not guaranteed achieved rates.

Raw preview is JPEG quality75, AI annotated latest image defaults95, atomically replaced. AI metrics/health are separate atomic JSON snapshots; an image and adjacent JSON read are not guaranteed the same exposure. Backend freshness verifies source, health, generation, timestamp and maximum AI age5s; heartbeat cutoff10s. The AI MJPEG stream rechecks currentness every.25s. Raw preview only checks ONLINE at open; frontend polling/expiry mitigates stale display, but the raw stream itself lacks the same continuous callback.

Evidence: [ai/frame_source.py:114](/Users/abcd/cityeye-ai/ai/frame_source.py:114), [ai/process_video.py:344](/Users/abcd/cityeye-ai/ai/process_video.py:344), [backend/app/live_camera.py:74](/Users/abcd/cityeye-ai/backend/app/live_camera.py:74), [backend/app/main.py:838](/Users/abcd/cityeye-ai/backend/app/main.py:838).

### Recorded assets verified now

| Scenario | Input metadata | CSV observations | Detection / processed frames | Current event artifacts | AI state frame counts |
| --- | --- | --- | --- | --- | --- |
| congestion | 3840×2160; 13.566667s | 12604 | 407 / 407 | CONGESTION@5.0 | {"MODERATE": 150, "HEAVY_CONGESTION": 257} |
| maydan_palestine | 1024×576; 312.150000s | 52689 | 6243 / 6243 | None | {"NORMAL": 5665, "MODERATE": 578} |
| normal_traffic | 3840×2160; 14.880000s | 4477 | 372 / 372 | None | {"NORMAL": 127, "MODERATE": 245} |
| rainy_traffic | 1080×1920; 13.129783s | 1632 | 611 / 787 | None | {"NORMAL": 787} |
| stopped_vehicle | 1920×1080; 10.600000s | 1640 | 318 / 318 | STOPPED_VEHICLE@4.0 | {"NORMAL": 318} |

All five registered annotated outputs are H.264 MP4 and have readable metadata; these files were not regenerated. Normal/congestion retain3840×2160, rain1080×1920, Maydan1024×576; the stopped annotated output is1280×720 while its current input is1920×1080. That mismatch and historical event replacement mean identical run lineage is **NOT VERIFIED**. `stopped_vehicle_candidate.mp4` is another local candidate; `stopped_vehicle_2` output exists but is not registered in `SCENARIOS` and has no traffic timeline.

**Maydan Palestine specifically:** registered as Palestine Square;6243 frames at20FPS,312.15s;52,689 CSV road-user observations, zero event artifacts. The annotated30s frame visibly contains cars and track IDs, so the integration is substantive. Observations are not52,689 unique vehicles. Config uses0,0 geographic coordinates and a broad rectangle `(0,60)–(1024,576)` rather than an evidence-approved road-only polygon; global vector `(512,520)→(512,80)` is not proof of lawful direction through a multi-approach junction. Wrong-way min displacement10,000px, stopped60s and congestion99vehicles/60s make positive demonstrations restrictive. Moderate threshold still defaults12;578 timeline frames say MODERATE. This is a detection/tracking playback demo, **not a validated location/calibration/event system** for the square.

The Cameras page describes all registered clips as municipal test footage, but stopped video's registry attributes an external stock-video URL. A file title is not evidence of municipal ownership or licensing. Usage rights and exact municipal location are **NOT VERIFIED**; no external market/source research was done.

Evidence: [backend/app/scenarios.py:1](/Users/abcd/cityeye-ai/backend/app/scenarios.py:1), [ai/config/scenarios/maydan_palestine.json:1](/Users/abcd/cityeye-ai/ai/config/scenarios/maydan_palestine.json:1), [ai/config/scenarios/stopped_vehicle.json:1](/Users/abcd/cityeye-ai/ai/config/scenarios/stopped_vehicle.json:1), [frontend/src/pages/CamerasPage.tsx:230](/Users/abcd/cityeye-ai/frontend/src/pages/CamerasPage.tsx:230). Metadata and scenario counts are embedded in JSON.

## 7. Incident lifecycle: what works and where it stops

### Live path

1. YOLO/ByteTrack observations reach enabled calibrated spatial/temporal rules.
2. A rule match receives a UUID, type, source-related details, timestamp, confidence, severity and explanation; status is PROPOSED.
3. The worker writes an actual annotated JPEG first, appends the event and atomically replaces `events.json`. In RTSP mode filenames include time/random suffix; existing delivery events are loaded on producer restart.
4. Backend startup and2s importer read per-camera events, force LIVE_CAMERA/source_id and PROPOSED for new inserts, verify safe existing complete JPG bytes and call `ingest_once`.
5. SQLite `events_v2` is authoritative for persistent live incident history. Retry of same UUID does not overwrite a human decision. Cross-source UUID reassignment is rejected; a legacy null-source row may be adopted without resetting status.
6. `/api/events` lists history; selected live event GET also runs importer reconciliation. Incidents keeps persistent LIVE_CAMERA rows and recorded scenario rows separately. Evidence routes bind source and filename.
7. ADMIN/EMPLOYEE Verify/Dismiss updates event status and writes audit in one transaction. Rollback-on-audit-failure, concurrent duplicate replay, missing-image retry, source isolation and restart behavior have passing existing integration tests.

### Recorded path

Scenario `events.json` is directly listed; DB state is merged by UUID when present. Review lazily inserts an absent proposal, then reviews it. There is **no equivalent automatic background recorded-scenario importer**. A new unreviewed scenario file can be visible without a DB row. Current review conversion does not inject RECORDED_SCENARIO/source_id if the artifact lacks them; the saved congestion row has both null. UI can still route its evidence via selected scenario, but durable source provenance is incomplete.

Recorded filenames such as `event_0001_*.jpg` can be reused on regenerated runs while new UUIDs differ. The DB stores a path reference, not immutable evidence bytes/hash. If a recorded event disappears from current scenario files, Incidents excludes its persisted row unless it is LIVE_CAMERA; historical recorded DB persistence is therefore not identical to guaranteed UI history retention.

### Actual database examples

| Event | Type / source | Status now | What it proves | What it does not prove |
| --- | --- | --- | --- | --- |
| 70197f71-3dce-4982-9c22-7ddb5e8164ba | WRONG_WAY / LIVE_CAMERA camera-3 | VERIFIED | Old live proposal persisted and reviewed; referenced image exists | Correct direction calibration or reliable live Wrong Way; current rule disabled |
| 35b9c58c-3051-4d46-a049-0aa1a916dd94 | STOPPED_VEHICLE / RECORDED_SCENARIO stopped_vehicle | DISMISSED | Historical explicitly labeled bbox-jitter false proposal, actual review/evidence path | A valid naturally moved-then-stopped vehicle |
| f1c156e1-cf13-441c-a9f1-e0b1d105019a | CONGESTION / null source identity | VERIFIED | Recorded congestion row exists, associated scenario image exists | Live Camera3 congestion or complete source lineage |

All three referenced evidence basenames were found in their expected current source directories. The generic congestion basename also exists in older default output directories with different sizes, illustrating why source-bound paths matter. No incident was created or reviewed during this audit.

Deduplication has several scopes: rule episode/track suppression, same UUID DB insertion, and retry delivery. These do **not** imply physical-vehicle deduplication across restarts, reruns or ID switches. Recreating temporal state can produce a new UUID for a later/reobserved physical condition. Backend review currently permits changing a previously reviewed status; the frontend disables buttons for non-PROPOSED rows, but that UI restriction is not a backend transition invariant. Concurrent reviewers have no optimistic version check.

The most material broken UI link is failure acknowledgment: recorded `useEvents.decide` catches an error without returning failure, while Command Center then changes dialog status optimistically. A failed DB save can therefore look locally verified/dismissed. This is a verified code-path finding, not a production mutation reproduced during the audit. Live review also lacks a catch/error display in its decision handler. Existing positive mocked UI tests do not cover every rejection/race case.

Evidence: [ai/event_pipeline.py:211](/Users/abcd/cityeye-ai/ai/event_pipeline.py:211), [backend/app/live_incidents.py:1](/Users/abcd/cityeye-ai/backend/app/live_incidents.py:1), [backend/app/database.py:255](/Users/abcd/cityeye-ai/backend/app/database.py:255), [backend/app/database.py:279](/Users/abcd/cityeye-ai/backend/app/database.py:279), [backend/app/main.py:937](/Users/abcd/cityeye-ai/backend/app/main.py:937), [frontend/src/pages/IncidentsPage.tsx:43](/Users/abcd/cityeye-ai/frontend/src/pages/IncidentsPage.tsx:43), [frontend/src/pages/MunicipalDashboard.tsx:546](/Users/abcd/cityeye-ai/frontend/src/pages/MunicipalDashboard.tsx:546), [backend/tests/test_live_incidents.py:1](/Users/abcd/cityeye-ai/backend/tests/test_live_incidents.py:1).

## 8. Backend API catalog

All 47 explicitly declared GET/POST/PATCH route operations were extracted from current `main.py` without starting the application. The table's IMPLEMENTED status is a code/control-test finding; it is not a claim that every protected endpoint was exercised against the current live server. Read-only HTTP checks are listed in section14 and JSON.

Authentication here describes **current auth-required mode**. In explicitly auth-disabled non-production mode, the backend supplies demo ADMIN and ingestion bypasses token checks. Public endpoints are health, login/session, token-protected machine ingest (public to human-session middleware), and citizen POST. CITIZEN middleware allows only session/logout and report read/create surfaces; other product APIs/media are blocked. User management is ADMIN only; all incident review is ADMIN/EMPLOYEE.

| Endpoint | Purpose | Authentication / roles | Input | Output | DB / storage | Frontend use | Status / known issue | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| POST /api/auth/login | login | Public credentials; All active accounts | credentials | LoginResponse | Create session + audit | Login | IMPLEMENTED; runtime scope noted; No throttling; no login executed during read-only audit | [backend/app/main.py:492](/Users/abcd/cityeye-ai/backend/app/main.py:492) |
| GET /api/auth/session | auth session | Optional session; All | None | SessionResponse | Resolve session/users | App bootstrap/focus/30s | IMPLEMENTED; runtime scope noted; Anonymous HTTP200 observed | [backend/app/main.py:527](/Users/abcd/cityeye-ai/backend/app/main.py:527) |
| POST /api/auth/logout | logout | Session; All signed-in roles | None | LogoutResponse | Delete session + audit | Header | IMPLEMENTED; runtime scope noted; Existing isolated tests only | [backend/app/main.py:539](/Users/abcd/cityeye-ai/backend/app/main.py:539) |
| GET /api/audit | audit log | Session; ADMIN / EMPLOYEE | None | AuditListResponse | Audit rows | No audit page found | IMPLEMENTED; runtime scope noted; Operational staff may read audit; backend capability not exposed as a page | [backend/app/main.py:558](/Users/abcd/cityeye-ai/backend/app/main.py:558) |
| GET /api/users | list users | Session; ADMIN | None | UserListResponse | Users read | User Access | IMPLEMENTED; runtime scope noted; No subscriptions; no password recovery API | [backend/app/main.py:565](/Users/abcd/cityeye-ai/backend/app/main.py:565) |
| POST /api/users | create user | Session; ADMIN | payload | UserResponse | Users update/create + audit; disable revokes sessions | User Access | IMPLEMENTED; runtime scope noted; No subscriptions; no password recovery API | [backend/app/main.py:577](/Users/abcd/cityeye-ai/backend/app/main.py:577) |
| PATCH /api/users/{user_id} | update user | Session; ADMIN | user_id, payload | UserResponse | Users update/create + audit; disable revokes sessions | User Access | IMPLEMENTED; runtime scope noted; No subscriptions; no password recovery API | [backend/app/main.py:600](/Users/abcd/cityeye-ai/backend/app/main.py:600) |
| GET /health | health | Public; All | None | HealthResponse | None | Header/readiness and container probes | IMPLEMENTED; runtime scope noted; HTTP200 observed; readiness does not guarantee live camera health | [backend/app/main.py:623](/Users/abcd/cityeye-ai/backend/app/main.py:623) |
| GET /health/live | liveness | Public; All | None | HealthResponse | None | Header/readiness and container probes | IMPLEMENTED; runtime scope noted; HTTP200 observed; readiness does not guarantee live camera health | [backend/app/main.py:628](/Users/abcd/cityeye-ai/backend/app/main.py:628) |
| GET /health/ready | readiness | Public; All | None | ReadinessResponse | DB health read | Header/readiness and container probes | IMPLEMENTED; runtime scope noted; HTTP200 observed; readiness does not guarantee live camera health | [backend/app/main.py:638](/Users/abcd/cityeye-ai/backend/app/main.py:638) |
| GET /api/live-camera/status | live camera status | Session; ADMIN / EMPLOYEE | None | CameraHealthResponse | Health/metrics files | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Code/tests pass; protected runtime requires existing session; root-output path differs from per-camera path | [backend/app/main.py:660](/Users/abcd/cityeye-ai/backend/app/main.py:660) |
| GET /api/live-camera/metrics | live camera metrics | Session; ADMIN / EMPLOYEE | None | LiveMetricsSnapshot | Health/metrics files | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Code/tests pass; protected runtime requires existing session; root-output path differs from per-camera path | [backend/app/main.py:671](/Users/abcd/cityeye-ai/backend/app/main.py:671) |
| GET /api/live-camera/events | live camera events | Session; ADMIN / EMPLOYEE | None | EventListResponse | Files merged with DB | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Selected live GET invokes sync and can mutate DB; not called in audit; root-output path differs from per-camera path | [backend/app/main.py:678](/Users/abcd/cityeye-ai/backend/app/main.py:678) |
| POST /api/live-camera/events/{event_id}/verify | verify live event | Session; ADMIN / EMPLOYEE | event_id | TrafficEventResponse | Review + atomic audit; scenario/legacy may insert first | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Scenario lazy insert can lack source_id; status transition not restricted to PROPOSED on backend; root-output path differs from per-camera path | [backend/app/main.py:696](/Users/abcd/cityeye-ai/backend/app/main.py:696) |
| POST /api/live-camera/events/{event_id}/dismiss | dismiss live event | Session; ADMIN / EMPLOYEE | event_id | TrafficEventResponse | Review + atomic audit; scenario/legacy may insert first | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Scenario lazy insert can lack source_id; status transition not restricted to PROPOSED on backend; root-output path differs from per-camera path | [backend/app/main.py:700](/Users/abcd/cityeye-ai/backend/app/main.py:700) |
| GET /media/live-camera.mjpg | live camera stream | Session; ADMIN / EMPLOYEE | None | FileResponse / StreamingResponse | None; filesystem/stream | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Authenticated browser streaming not revalidated this audit; root-output path differs from per-camera path | [backend/app/main.py:704](/Users/abcd/cityeye-ai/backend/app/main.py:704) |
| GET /evidence/live/{filename} | live camera evidence | Session; ADMIN / EMPLOYEE | filename | FileResponse / StreamingResponse | None; filesystem read | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Filesystem persistence separate from DB backups; root-output path differs from per-camera path | [backend/app/main.py:715](/Users/abcd/cityeye-ai/backend/app/main.py:715) |
| GET /api/live-cameras | live cameras | Session; ADMIN / EMPLOYEE | None | list[CameraHealthResponse] | Health/metrics files | Live pages | IMPLEMENTED; runtime scope noted; Code/tests pass; protected runtime requires existing session | [backend/app/main.py:724](/Users/abcd/cityeye-ai/backend/app/main.py:724) |
| GET /api/live-cameras/{camera_id}/status | selected live camera status | Session; ADMIN / EMPLOYEE | camera_id | CameraHealthResponse | Health/metrics files | Live pages | IMPLEMENTED; runtime scope noted; Code/tests pass; protected runtime requires existing session | [backend/app/main.py:742](/Users/abcd/cityeye-ai/backend/app/main.py:742) |
| GET /api/live-cameras/{camera_id}/metrics | selected live camera metrics | Session; ADMIN / EMPLOYEE | camera_id | LiveMetricsSnapshot | Health/metrics files | Live pages | IMPLEMENTED; runtime scope noted; Code/tests pass; protected runtime requires existing session | [backend/app/main.py:752](/Users/abcd/cityeye-ai/backend/app/main.py:752) |
| GET /api/analytics/traffic | operational traffic analytics | Session; ADMIN / EMPLOYEE | camera_id, start, end | OperationalAnalyticsResponse | traffic_observations + events_v2 | Analytics | IMPLEMENTED; runtime scope noted; Camera-name incident association, sparse-sample duration | [backend/app/main.py:762](/Users/abcd/cityeye-ai/backend/app/main.py:762) |
| GET /api/live-cameras/{camera_id}/events | selected live camera events | Session; ADMIN / EMPLOYEE | camera_id | EventListResponse | Importer may write, then DB read | Command Center/Cameras; scenarios also Incidents | IMPLEMENTED; runtime scope noted; Selected live GET invokes sync and can mutate DB; not called in audit | [backend/app/main.py:785](/Users/abcd/cityeye-ai/backend/app/main.py:785) |
| POST /api/live-cameras/{camera_id}/events/{event_id}/verify | verify selected live event | Session; ADMIN / EMPLOYEE | camera_id, event_id | TrafficEventResponse | Review + atomic audit; scenario/legacy may insert first | Command Center/Incidents | IMPLEMENTED; runtime scope noted; Scenario lazy insert can lack source_id; status transition not restricted to PROPOSED on backend | [backend/app/main.py:808](/Users/abcd/cityeye-ai/backend/app/main.py:808) |
| POST /api/live-cameras/{camera_id}/events/{event_id}/dismiss | dismiss selected live event | Session; ADMIN / EMPLOYEE | camera_id, event_id | TrafficEventResponse | Review + atomic audit; scenario/legacy may insert first | Command Center/Incidents | IMPLEMENTED; runtime scope noted; Scenario lazy insert can lack source_id; status transition not restricted to PROPOSED on backend | [backend/app/main.py:816](/Users/abcd/cityeye-ai/backend/app/main.py:816) |
| GET /media/live-cameras/{camera_id}.mjpg | selected live camera stream | Session; ADMIN / EMPLOYEE | camera_id | FileResponse / StreamingResponse | None; filesystem/stream | Video/preview | IMPLEMENTED; runtime scope noted; Authenticated browser streaming not revalidated this audit | [backend/app/main.py:820](/Users/abcd/cityeye-ai/backend/app/main.py:820) |
| GET /media/live-cameras/{camera_id}/preview.mjpg | selected live camera preview | Session; ADMIN / EMPLOYEE | camera_id | FileResponse / StreamingResponse | None; filesystem/stream | Video/preview | IMPLEMENTED; runtime scope noted; Raw MJPEG freshness check only at start | [backend/app/main.py:838](/Users/abcd/cityeye-ai/backend/app/main.py:838) |
| GET /evidence/live-cameras/{camera_id}/{filename} | selected live camera evidence | Session; ADMIN / EMPLOYEE | camera_id, filename | FileResponse / StreamingResponse | None; filesystem read | Incident image | IMPLEMENTED; runtime scope noted; Filesystem persistence separate from DB backups | [backend/app/main.py:857](/Users/abcd/cityeye-ai/backend/app/main.py:857) |
| GET /api/analysis/summary | analysis summary | Session; ADMIN / EMPLOYEE | None | AnalysisSummary | CSV/timeline files | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Timeline omits zero-detection frames; summary last detection frame; root-output path differs from per-camera path | [backend/app/main.py:867](/Users/abcd/cityeye-ai/backend/app/main.py:867) |
| GET /api/analysis/timeline | analysis timeline | Session; ADMIN / EMPLOYEE | None | AnalysisTimeline | CSV/timeline files | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Timeline omits zero-detection frames; summary last detection frame; root-output path differs from per-camera path | [backend/app/main.py:876](/Users/abcd/cityeye-ai/backend/app/main.py:876) |
| GET /media/annotated.mp4 | annotated video | Session; ADMIN / EMPLOYEE | None | FileResponse / StreamingResponse | None; filesystem/stream | Legacy/default-output compatibility; no current normal frontend consumer | IMPLEMENTED; runtime scope noted; Authenticated browser streaming not revalidated this audit; root-output path differs from per-camera path | [backend/app/main.py:885](/Users/abcd/cityeye-ai/backend/app/main.py:885) |
| GET /api/scenarios | list scenarios | Session; ADMIN / EMPLOYEE | None | ScenarioListResponse | None; static registry | Sidebar/Cameras | IMPLEMENTED; runtime scope noted; Five hardcoded scenario entries; no dynamic upload registry | [backend/app/main.py:906](/Users/abcd/cityeye-ai/backend/app/main.py:906) |
| GET /api/scenarios/{scenario_id}/analysis/summary | scenario summary | Session; ADMIN / EMPLOYEE | scenario_id | AnalysisSummary | CSV/timeline files | Recorded analysis | IMPLEMENTED; runtime scope noted; Timeline omits zero-detection frames; summary last detection frame | [backend/app/main.py:910](/Users/abcd/cityeye-ai/backend/app/main.py:910) |
| GET /api/scenarios/{scenario_id}/analysis/timeline | scenario timeline | Session; ADMIN / EMPLOYEE | scenario_id | AnalysisTimeline | CSV/timeline files | Recorded analysis | IMPLEMENTED; runtime scope noted; Timeline omits zero-detection frames; summary last detection frame | [backend/app/main.py:914](/Users/abcd/cityeye-ai/backend/app/main.py:914) |
| GET /api/scenarios/{scenario_id}/events | scenario events | Session; ADMIN / EMPLOYEE | scenario_id | EventListResponse | Files merged with DB | Command Center/Cameras; scenarios also Incidents | IMPLEMENTED; runtime scope noted; Selected live GET invokes sync and can mutate DB; not called in audit | [backend/app/main.py:918](/Users/abcd/cityeye-ai/backend/app/main.py:918) |
| POST /api/scenarios/{scenario_id}/events/{event_id}/verify | verify scenario event | Session; ADMIN / EMPLOYEE | scenario_id, event_id | TrafficEventResponse | Review + atomic audit; scenario/legacy may insert first | Command Center/Incidents | IMPLEMENTED; runtime scope noted; Scenario lazy insert can lack source_id; status transition not restricted to PROPOSED on backend | [backend/app/main.py:953](/Users/abcd/cityeye-ai/backend/app/main.py:953) |
| POST /api/scenarios/{scenario_id}/events/{event_id}/dismiss | dismiss scenario event | Session; ADMIN / EMPLOYEE | scenario_id, event_id | TrafficEventResponse | Review + atomic audit; scenario/legacy may insert first | Command Center/Incidents | IMPLEMENTED; runtime scope noted; Scenario lazy insert can lack source_id; status transition not restricted to PROPOSED on backend | [backend/app/main.py:964](/Users/abcd/cityeye-ai/backend/app/main.py:964) |
| GET /media/scenarios/{scenario_id}/annotated.mp4 | scenario video | Session; ADMIN / EMPLOYEE | scenario_id | FileResponse / StreamingResponse | None; filesystem/stream | Video/preview | IMPLEMENTED; runtime scope noted; Authenticated browser streaming not revalidated this audit | [backend/app/main.py:975](/Users/abcd/cityeye-ai/backend/app/main.py:975) |
| GET /evidence/scenarios/{scenario_id}/{filename} | scenario evidence | Session; ADMIN / EMPLOYEE | scenario_id, filename | FileResponse / StreamingResponse | None; filesystem read | Incident image | IMPLEMENTED; runtime scope noted; Filesystem persistence separate from DB backups | [backend/app/main.py:982](/Users/abcd/cityeye-ai/backend/app/main.py:982) |
| POST /api/events/ingest | ingest event | X-CityEye-Ingest-Token when auth required; Machine | event | TrafficEventResponse | Insert PROPOSED; UUID duplicate409 | AI/client integration; live worker uses file importer | IMPLEMENTED; runtime scope noted; Not the automatic live delivery transport; general ingestion does not check image exists | [backend/app/main.py:992](/Users/abcd/cityeye-ai/backend/app/main.py:992) |
| GET /api/events | list events | Session; ADMIN / EMPLOYEE | None | EventListResponse | events_v2 read | Incidents uses list; single read API not directly used | IMPLEMENTED; runtime scope noted; Unpaginated; video seconds and Unix timestamps coexist | [backend/app/main.py:1011](/Users/abcd/cityeye-ai/backend/app/main.py:1011) |
| GET /api/events/{event_id} | get event | Session; ADMIN / EMPLOYEE | event_id | TrafficEventResponse | events_v2 read | Incidents uses list; single read API not directly used | IMPLEMENTED; runtime scope noted; Unpaginated; video seconds and Unix timestamps coexist | [backend/app/main.py:1023](/Users/abcd/cityeye-ai/backend/app/main.py:1023) |
| POST /api/events/{event_id}/verify | verify event | Session; ADMIN / EMPLOYEE | event_id | TrafficEventResponse | Review + atomic audit; scenario/legacy may insert first | Command Center/Incidents | IMPLEMENTED; runtime scope noted; Scenario lazy insert can lack source_id; status transition not restricted to PROPOSED on backend | [backend/app/main.py:1041](/Users/abcd/cityeye-ai/backend/app/main.py:1041) |
| POST /api/events/{event_id}/dismiss | dismiss event | Session; ADMIN / EMPLOYEE | event_id | TrafficEventResponse | Review + atomic audit; scenario/legacy may insert first | Command Center/Incidents | IMPLEMENTED; runtime scope noted; Scenario lazy insert can lack source_id; status transition not restricted to PROPOSED on backend | [backend/app/main.py:1054](/Users/abcd/cityeye-ai/backend/app/main.py:1054) |
| POST /api/citizen-reports | create citizen report | Public; All incl CITIZEN | report | CitizenReportResponse | Insert + cluster/update | Citizen list GET only; no POST form | IMPLEMENTED; runtime scope noted; Client demo identity; no operational anti-abuse | [backend/app/main.py:1068](/Users/abcd/cityeye-ai/backend/app/main.py:1068) |
| GET /api/citizen-reports | list citizen reports | Session; All incl CITIZEN | None | CitizenReportListResponse | Citizen report read | Citizen list GET only; no POST form | IMPLEMENTED; runtime scope noted; Client demo identity; no operational anti-abuse | [backend/app/main.py:1082](/Users/abcd/cityeye-ai/backend/app/main.py:1082) |
| GET /api/citizen-reports/{report_id} | get citizen report | Session; All incl CITIZEN | report_id | CitizenReportResponse | Citizen report read | Citizen list GET only; no POST form | IMPLEMENTED; runtime scope noted; Client demo identity; no operational anti-abuse | [backend/app/main.py:1096](/Users/abcd/cityeye-ai/backend/app/main.py:1096) |
| GET /evidence/{filename} | get evidence | Session; ADMIN / EMPLOYEE | filename | FileResponse / StreamingResponse | None; filesystem read | Incident image | IMPLEMENTED; runtime scope noted; Filesystem persistence separate from DB backups | [backend/app/main.py:1116](/Users/abcd/cityeye-ai/backend/app/main.py:1116) |

**Compatibility and unused surfaces:** singular `/api/live-camera/*`, default `/api/analysis/*` and `/media/annotated.mp4` target legacy root output rather than the current selected-camera/scenario structure. They remain implemented and tested; absence from current frontend consumers does not prove they are globally dead. `/api/audit` and individual event/report GET exist without dedicated UI pages. Machine ingestion is useful but the current live producer uses mounted files/importer instead of posting HTTP. The frontend's `authorizationHeaders()` returns undefined because authentication moved to same-origin cookies; it is compatibility scaffolding, not bearer-token storage.

**Contract and operational issues:** full lists have no pagination; analysis reparses CSV on request; all scenarios are hardcoded; selected live event GET can write through `sync_safely` and was intentionally not used for the read-only audit. That GET side effect should be documented or removed in a later task. No dynamic upload/start-inference API, camera-configuration management API, forecast API, subscriptions API, dispatch API or settings API was found. Road-blockage details are structurally validated by the backend, so the frontend's typed numeric rendering is not evidence of a reproduced malformed-backend crash. No claim that a historical black screen still occurs is warranted without a current reproduction.

Evidence: [frontend/src/api/auth.ts:15](/Users/abcd/cityeye-ai/frontend/src/api/auth.ts:15), [backend/app/main.py:785](/Users/abcd/cityeye-ai/backend/app/main.py:785), [backend/app/schemas.py:126](/Users/abcd/cityeye-ai/backend/app/schemas.py:126), [backend/app/analysis.py:1](/Users/abcd/cityeye-ai/backend/app/analysis.py:1).

## 9. Database and persistence audit

SQLite is the sole operational DB in the audited stack. Current container DB: `/data/cityeye.db`,458,752 bytes at the first inspection; its size is a snapshot. It is persisted in `cityeye-ai_cityeye_database`. Read-only SQL URI used `mode=ro`, with schema queries, counts, `PRAGMA quick_check` and `foreign_key_check`; no SQL mutation or initializer was run against it.

Snapshot UTC: 2026-09-24T15:44:18.186507+00:00. Quick check: **ok**; foreign-key violations: **none**. This checks structural consistency, not evidence correctness or security. Full table/index SQL and aggregate records are in JSON; passwords, session hashes/tokens and private usernames are omitted.

| Table | Rows at snapshot | Purpose and key fields | Relationships/indexes/limitations |
| --- | --- | --- | --- |
| events | 0 | Legacy three-event schema; retained by migration | event_id PK, timestamp/status indexes; current repository operates on events_v2 |
| events_v2 | 3 | UUID/type/time/confidence/severity/explanation/camera/location/evidence/details_json/status/source fields | PK UUID; timestamp/status indexes; source fields nullable, no camera FK or source index; mixed time domains |
| traffic_observations | 2329 | camera/interval/observed_at/generation/class counts/movement/state/capture+AI FPS | Unique(camera_id,interval_start); camera/time index; no camera registry FK; no retention |
| users | 3 | ID/username/password_hash/role/active/created | Unique NOCASE username;3-role CHECK; one active account per role at snapshot |
| auth_sessions | 1 | SHA256 token hash/user_id/expiry/created | Declared FK users with ON DELETE CASCADE; expiry index; auth connector does not enable PRAGMA foreign_keys |
| audit_log | 89 | Actor identity snapshot/action/target/previous/new/requestID/time | audit_id PK/time index; no FK binding actor/target; retaining historical snapshot intentional but not tamper-evident |
| citizen_reports | 0 | Category/description/coordinate/demo_user_id/reported_at/status | PK report_id; category/time index; no authenticated-user FK; confirmation updates matching reports |
| sqlite_sequence | 1 | SQLite auto-increment bookkeeping | Internal; not a domain feature |

Relationships are mostly application-level. There is no DB camera table, separate event-evidence table, municipal organization/tenant table, dispatch record, subscription record or calibration-history table. Evidence references are relative filesystem strings; row existence does not guarantee file survival. Normal application authentication explicitly deletes sessions when disabling an account and re-resolves active role on requests; do not rely on the declared cascade when foreign-key enforcement is not enabled by its connector.

Event review and corresponding audit insert are atomic. Account creation/access change and their audit recording are separate repository calls, so their transactional guarantees are weaker. UUID uniqueness prevents identical delivery duplication, not semantically duplicate detections assigned new IDs. Source identity can be null for old/lazy recorded rows. Raw SQL schema contains fewer source invariants than Pydantic validation; there is no versioned migration framework, only initialization/migration code. Role migration maps legacy OPERATOR/REVIEWER→EMPLOYEE and preserves IDs/sessions/passwords; current schema confirms the new roles.

Backups are implemented using SQLite backup, integrity verification, checksummed manifest, atomic publication and default retention14 daily copies. **The current backup service is absent from `docker compose ps -a`, and no backup named volume was listed.** Three historical manually named DB snapshots remain in `/data`; these are not proof of a working current scheduler. Backup code only covers SQLite; video/evidence/config/secrets recovery must be designed separately. Restore was tested in temporary databases by the existing suite, not against production. No off-host copy, recovery objective or recent full disaster-recovery drill was verified. No automated retention/purge was found for live events/evidence/observations/audit logs.

Evidence: [backend/app/database.py:1](/Users/abcd/cityeye-ai/backend/app/database.py:1), [backend/app/auth.py:112](/Users/abcd/cityeye-ai/backend/app/auth.py:112), [backend/app/auth.py:118](/Users/abcd/cityeye-ai/backend/app/auth.py:118), [backend/app/main.py:577](/Users/abcd/cityeye-ai/backend/app/main.py:577), [backend/app/backups.py:1](/Users/abcd/cityeye-ai/backend/app/backups.py:1), [compose.yaml:68](/Users/abcd/cityeye-ai/compose.yaml:68).

## 10. Frontend audit

Current routes are guarded after session restoration. `/dashboard` redirects to Command Center; `/map` redirects to Citizen Map; unknown routes redirect through the same role gating. There is no Settings page. Current-source TypeScript/build and59 jsdom tests passed; a freshly opened real browser displayed the Login page without captured console errors. Full authenticated visual/responsive/navigation and live Verify execution remain **NOT VERIFIED** this audit because no valid session was available and the task forbids DB changes.

### Login /login


| Aspect | Finding |
| --- | --- |
| Purpose | Authenticated entry |
| Data | auth session + login |
| Roles | All; Citizen redirected to map |
| Functionality | Credential form, show-password, pending/failed/success motion, reduced-motion tests |
| Loading | Bootstrap + submit pending |
| Empty | Blank credential form |
| Error | Safe credential/service messages |
| Freshness | Session bootstrap; active session focus/30s checks |
| Visual | Current1280×720 screenshot rendered; no console errors; no sign-in attempted |
| Issues | Visual shell says municipal/authorized personnel even Citizen entry; password recovery absent |

Evidence: [frontend/src/pages/LoginPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/LoginPage.tsx:1); [frontend/src/hooks/useAuth.ts:1](/Users/abcd/cityeye-ai/frontend/src/hooks/useAuth.ts:1).

### Command Center /command-center


| Aspect | Finding |
| --- | --- |
| Purpose | Source viewing and incident triage |
| Data | Scenarios/summary/timeline/events; live cameras/metrics/events; MP4/MJPEG |
| Roles | ADMIN/EMPLOYEE |
| Functionality | Select live/recorded; raw/AI live view; playback-relative metrics/events; View/Verify/Dismiss |
| Loading | Waiting-for-AI/video placeholder; fetch/error states |
| Empty | No matching/visible incident state |
| Error | Data fetch errors shown; live review rejection not caught locally |
| Freshness | Live2s polling,4s timeout, local250ms expiry tick; recorded event2s poll; summary/timeline once per source |
| Visual | Authenticated current browser view NOT VERIFIED; source/test review only |
| Issues | I03 optimistic failed recorded review; I04 carried counts; recorded hooks still load normal scenario in live mode; stale review races possible |

Evidence: [frontend/src/pages/MunicipalDashboard.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/MunicipalDashboard.tsx:1); [frontend/src/hooks/useEvents.ts:1](/Users/abcd/cityeye-ai/frontend/src/hooks/useEvents.ts:1).

### Cameras /cameras


| Aspect | Finding |
| --- | --- |
| Purpose | Configured source inventory |
| Data | Scenario snapshots and live status/metrics/events |
| Roles | ADMIN/EMPLOYEE |
| Functionality | Search, ALL/ONLINE/OFFLINE/INCIDENTS, grid/list, live previews and recorded video thumbnails |
| Loading | Recorded loading explicit; live initially absent |
| Empty | No live cameras banner also used after fetch error/filter zero |
| Error | Recorded error explicit; live error becomes empty list |
| Freshness | Live2s/4s timeout; recorded fetch on mount only |
| Visual | Grid/list glyph buttons lack descriptive accessible names; no current authenticated visual measurement |
| Issues | Recorded ONLINE filter means artifact READY; Current vehicles is last detection frame, not live; no add/edit camera functionality |

Evidence: [frontend/src/pages/CamerasPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/CamerasPage.tsx:1).

### Incidents /incidents


| Aspect | Finding |
| --- | --- |
| Purpose | Cross-source review/history |
| Data | Persistent events filtered LIVE_CAMERA + current scenario file events merged with DB |
| Roles | ADMIN/EMPLOYEE |
| Functionality | Status/high filters; evidence dialog; Verify/Dismiss |
| Loading | No explicit initial loading gate |
| Empty | May briefly say no real incidents before data arrives |
| Error | Separate live/recorded source errors and review retry message |
| Freshness | Persistent events2s; recorded snapshot once; successful local review updates both; no live-request deadline |
| Visual | Dialog lacks keyboard/focus management; current browser review NOT VERIFIED |
| Issues | Sort compares Unix live time and video-relative seconds; removed recorded artifacts vanish despite DB rows; detail banner stale |

Evidence: [frontend/src/pages/IncidentsPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/IncidentsPage.tsx:1); [frontend/src/components/Incident.tsx:1](/Users/abcd/cityeye-ai/frontend/src/components/Incident.tsx:1).

### Analytics /analytics


| Aspect | Finding |
| --- | --- |
| Purpose | Historical observations |
| Data | /api/analytics/traffic + camera inventory |
| Roles | ADMIN/EMPLOYEE |
| Functionality | Today/24h/7d/30d, camera, chart/composition/congestion/incidents/data quality |
| Loading | Explicit |
| Empty | Collection message with data-since |
| Error | Explicit + Retry |
| Freshness | Fetch on camera/range/retry only; Today uses browser timezone |
| Visual | SVG gaps equal-spaced; no quantitative Y labels; sampled observations disclaimer present |
| Issues | No forecast/multi-camera analytics; hardcoded disabled5/7 description; frame samples not throughput |

Evidence: [frontend/src/pages/AnalyticsPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/AnalyticsPage.tsx:1).

### Citizen Map /citizen-map


| Aspect | Finding |
| --- | --- |
| Purpose | Citizen public-traffic foundation |
| Data | GET citizen reports |
| Roles | All authenticated; only route available to CITIZEN |
| Functionality | First8 reports, category/status/coordinates; explicit map/corroboration placeholders |
| Loading | No dedicated loading state |
| Empty | No stored reports (current DB0) |
| Error | Inline error |
| Freshness | One mount fetch, no polling |
| Visual | Stylized map grid is decoration, no actual map |
| Issues | No map/provider/report creation form/clustering visualization; backend consensus not verified citizens |

Evidence: [frontend/src/pages/CitizenMapPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/CitizenMapPage.tsx:1).

### User Access /users


| Aspect | Finding |
| --- | --- |
| Purpose | Account administration |
| Data | GET/POST/PATCH users |
| Roles | ADMIN only; EMPLOYEE restricted; CITIZEN redirected |
| Functionality | Create accounts; role changes; enable/disable; final-admin protection in backend |
| Loading | Accounts loading + busy controls |
| Empty | No explicit empty panel; auth-required boot cannot start without accounts |
| Error | Readable role/save/duplicate errors |
| Freshness | Mount + after mutations; focus event triggers own role recheck |
| Visual | Bilingual role options; no current authenticated visual test |
| Issues | No password-reset/change or subscription management; all account admin denied to Employee |

Evidence: [frontend/src/pages/UsersPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/UsersPage.tsx:1).

### Settings


| Aspect | Finding |
| --- | --- |
| Purpose | Not present |
| Data | None |
| Roles | None |
| Functionality | NOT IMPLEMENTED |
| Loading | N/A |
| Empty | N/A |
| Error | Unknown route redirects |
| Freshness | N/A |
| Visual | No page |
| Issues | Do not describe configuration files as a settings UI |

Evidence: [frontend/src/App.tsx:1](/Users/abcd/cityeye-ai/frontend/src/App.tsx:1).

### Black-screen / Verify investigation scope

Existing tests verify safe rendering of wrong-way metadata, valid structured road-blockage details, source switching and successful review responses. STOPPED detail rendering now checks required numeric fields before `.toFixed`; it no longer treats every details object as stopped data. Backend ROAD_BLOCKAGE requires its structured numeric schema. Those are meaningful protections, but not proof every historical crash was repaired. No current black-screen was observed on the anonymous login page; protected View/Verify navigation was not executed. A specific historical crash's current reproduction is **NOT VERIFIED**.

Verified problems remain independent of a black-screen: recorded failed review can change dialog status incorrectly (I03); zero-detection playback gaps retain prior counts (I04); modal banner stays AI PROPOSED even after review; keyboard/focus and missing-image recovery are incomplete. `useEvents` polls without in-flight/deadline protection and does not invalidate a pending GET when a review completes; older responses can race local updates. Incidents has a review-version guard for its live list, while Command Center uses a different path. These are source-level race/failure risks, not incidents triggered against production during this audit.

Evidence: [frontend/src/pages/IncidentsPage.test.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/IncidentsPage.test.tsx:1), [frontend/src/App.test.tsx:315](/Users/abcd/cityeye-ai/frontend/src/App.test.tsx:315), [frontend/src/components/Incident.tsx:44](/Users/abcd/cityeye-ai/frontend/src/components/Incident.tsx:44), [frontend/src/hooks/useEvents.ts:1](/Users/abcd/cityeye-ai/frontend/src/hooks/useEvents.ts:1), [frontend/src/pages/MunicipalDashboard.tsx:490](/Users/abcd/cityeye-ai/frontend/src/pages/MunicipalDashboard.tsx:490).

## 11. Authentication, RBAC and security

### Current demo security that actually exists

Passwords use salted PBKDF2-HMAC-SHA256 with310,000 iterations,16 random salt bytes, constant-time comparison and minimum12 characters for account creation. Sessions use random opaque32-byte-url-safe tokens, storing only SHA256 hashes; default TTL8h, allowed5min–24h. Cookie `cityeye_session` is HttpOnly/SameSite=Strict/path=/; Secure is enabled only in production environment. Bearer sessions are supported by backend, but frontend uses cookies, not localStorage bearer credentials. Login failure/success, logout, account access changes and incident review are audited. Disabled users fail lookup and their sessions are revoked; role changes are re-resolved from DB on each request, frontend refreshes identity on focus/30s and clears on401.

Current deployment explicitly sets auth_required=true in demo mode. Anonymous attempts to live cameras, events, users, citizen report reads, recorded media and live evidence all returned401 through nginx. Tests establish ADMIN/EMPLOYEE/CITIZEN boundaries, session downgrade effects, user-administration denial and old-role migration. Three active accounts exist, one per current role. **OPERATOR and REVIEWER are legacy role names**, not valid current API roles; old docs/test descriptions and smoke tooling still contain them.

| Role | Operational data/review | Accounts | Citizen route |
| --- | --- | --- | --- |
| ADMIN | All current operations, Verify/Dismiss, audit read | Create/role/enable/disable; final-admin guard | Allowed |
| EMPLOYEE | All current operational pages and review; audit read | No list/create/update account administration | Allowed |
| CITIZEN | Denied operational API/media/evidence; redirected from operational pages | Denied | Only map/report foundation + auth lifecycle |

Employee implementation denies **all** account administration, broader than only forbidding account removal. There is no subscription/billing feature to cancel. Citizen map-only access does not mean a working geographic map exists.

Path traversal/symlink constraints protect media/evidence serving; request origin checks defend cookie writes, CORS has explicit validation, security headers restrict framing/content sources, and production configuration refuses auth-disabled mode/wildcard trusted hosts/insecure configured CORS origins. These are meaningful controls. Origin checks are not an anti-bot control: non-browser clients can omit Origin, and citizen POST intentionally remains public.

### Production security NOT established

Current nginx stack terminates plain HTTP; ports8000/5173 bind0.0.0.0 and IPv6 all interfaces. External firewall/router reachability is **NOT VERIFIED**. No native TLS termination, login rate limiting/lockout, MFA/SSO, password reset/change flow, credential rotation workflow or tenant authorization was found. Production environment validation alone does not create TLS, firewall policy or incident response. Login attempts produce audit entries without observed retention/rate bounds. Ingest token is a shared secret check; authentication is bypassed in explicitly disabled demo mode. Public citizen submissions use arbitrary demo identities, enabling fabricated community consensus if exposed operationally.

No vulnerability database scan, dependency CVE research, penetration testing or access-control attack was run. Dependency version pins and hardening code are not a certification of security. Camera credentials and private source addresses were not included in deliverables. DVR URL files/plists are deployment-local concerns and not browser-visible; actual source access control/network isolation was not independently verified.

Evidence: [backend/app/auth.py:1](/Users/abcd/cityeye-ai/backend/app/auth.py:1), [backend/app/main.py:449](/Users/abcd/cityeye-ai/backend/app/main.py:449), [backend/app/security.py:1](/Users/abcd/cityeye-ai/backend/app/security.py:1), [frontend/src/api/auth.ts:1](/Users/abcd/cityeye-ai/frontend/src/api/auth.ts:1), [backend/tests/test_role_access.py:1](/Users/abcd/cityeye-ai/backend/tests/test_role_access.py:1), [compose.yaml:31](/Users/abcd/cityeye-ai/compose.yaml:31), [scripts/smoke_test.py:151](/Users/abcd/cityeye-ai/scripts/smoke_test.py:151).

## 12. Analytics: exact meaning of the numbers

Historical analytics samples are collected from **fresh live metrics**, not demo fixtures. SQLite uniqueness stores the first accepted sample in each camera/minute interval; it does not aggregate every frame in that minute. Runtime snapshot had2329 Camera3 samples over a date span longer than2329 continuous minutes. The application can contain long gaps. These are real model observations, not verified vehicle ground truth.

| Metric | Source/calculation | Time window | Meaning/limits | Reality/validation | Evidence |
| --- | --- | --- | --- | --- | --- |
| Current vehicles | Accepted car/bus/truck/motorcycle frame rows; live len(rows), recorded distinct nonempty IDs + unassigned | Current AI frame / selected recorded detection frame | Visible detections, includes parked/outside ROI; not unique throughput | Real inferred observations; physical recall NOT VERIFIED | [ai/process_video.py:575](/Users/abcd/cityeye-ai/ai/process_video.py:575) |
| Cars / buses / trucks / motorcycles | Class-filtered frame observations; vehicle class stabilization window7 for IDs | Current frame | COCO prediction, not ground truth; category confusion possible | Real model outputs; accuracy NOT VERIFIED | [ai/process_video.py:536](/Users/abcd/cityeye-ai/ai/process_video.py:536) |
| People / bicycles | Accepted person/bicycle row counts | Current frame | Separate from motor vehicle count; ROI bottom-center metrics mainly recorded timeline | Real inferred counts; membership accuracy NOT VERIFIED | [ai/process_video.py:984](/Users/abcd/cityeye-ai/ai/process_video.py:984) |
| Active tracks | Unique current non-null track IDs across all road-user rows | Current frame | Includes people/bicycles; not cumulative vehicles or cross-camera identities | Controlled tests + limited historical real tracking | [ai/process_video.py:595](/Users/abcd/cityeye-ai/ai/process_video.py:595) |
| Moving / stationary / unknown | Current vehicle track movement state counts; unknown when road uncalibrated | Current frame, median speed history5 | Track state based on pixels/ROI scale; not physical velocity or eligible stop event | Controlled regressions; natural stop not established | [ai/trajectory.py:109](/Users/abcd/cityeye-ai/ai/trajectory.py:109) |
| Traffic NORMAL/MODERATE/HEAVY | Road ROI accepted vehicles .30 rule floor, density/spacing/motion/persistence | Current episode;5s live confirmation | .22 visible car can be excluded from .30 traffic rule; NORMAL not guaranteed clear road | Recorded congestion artifact; live positives NOT VALIDATED | [ai/event_rules.py:568](/Users/abcd/cityeye-ai/ai/event_rules.py:568) |
| FPS capture / preview / AI | Capture timestamp window5s; preview submission window; completed AI publication rolling rate | Rolling runtime window | Throughput/cadence, not sensor exposure latency; preview health count is callback accepted, not exact final JPEG delivery | Actual snapshots; not load benchmark | [ai/process_video.py:372](/Users/abcd/cityeye-ai/ai/process_video.py:372) |
| Average Vehicles Observed | Mean active vehicle count in stored observations | Requested time window | First valid sample per60s; missing time not filled; parked objects repeat | Actual DB samples; analytics tests | [backend/app/operational_analytics.py:91](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:91) |
| Vehicle composition | Sum class counts across stored samples | Requested time window | Repeated observations of same vehicle; not unique fleet composition; excludes people | Actual DB + controlled formula tests | [backend/app/operational_analytics.py:144](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:144) |
| Peak period / peak count | Bucket with maximum average count, count=that average | 5min ≤6h,15min ≤2d,60min longer | Label peak_vehicle_count is peak BUCKET AVERAGE, not max instantaneous count | Controlled tests; runtime display NOT VERIFIED | [backend/app/operational_analytics.py:133](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:133) |
| Congestion duration / episodes | MODERATE/HEAVY_CONGESTION/CONGESTED samples×60s; new episode after noncongested or >90s gap | Requested time range | Approximate occupancy of sampled state, not continuous sensor truth; MODERATE included | DB-driven formulas; calibrated live traffic truth NOT VERIFIED | [backend/app/operational_analytics.py:21](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:21) |
| Incidents | Persisted events matching camera_name and timestamp interval, all review statuses | Requested Unix interval | Recorded seconds not epoch; ignores most recorded rows; name join fragile; event confidence heuristic | Current DB3rows; controlled queries | [backend/app/operational_analytics.py:138](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:138) |
| Observed minutes | Stored sample count×sampling interval/60 | Requested window | Not guaranteed continuous uptime; gaps visible only via sparse samples | Actual samples; code verified | [backend/app/operational_analytics.py:177](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:177) |
| Recorded summary current count | Last frame present in tracks.csv | Last detection-bearing frame in output | Can differ from actual last video frame; not playback position | Current source reader inspected | [backend/app/analysis.py:75](/Users/abcd/cityeye-ai/backend/app/analysis.py:75) |
| Historical traffic chart | Mean counts by bucket and majority traffic state | Selected range | Frontend uses ordinal X positions, compresses long missing intervals | Data real; visual time spacing misleading | [frontend/src/pages/AnalyticsPage.tsx:32](/Users/abcd/cityeye-ai/frontend/src/pages/AnalyticsPage.tsx:32) |
| Prediction / LPR / speed km/h | Not implemented | None | No numbers should be claimed | NOT AVAILABLE | [frontend/src/pages/AnalyticsPage.tsx:106](/Users/abcd/cityeye-ai/frontend/src/pages/AnalyticsPage.tsx:106) |

No metric should be described as “vehicles passed today” or unique municipal traffic throughput. There is no entry/exit counting line, cross-session deduplication or persistent physical vehicle identity. A parked car counted every minute can contribute repeatedly to composition totals. People are stored but not included in vehicle-composition aggregation. Historical track totals are not a separate durable throughput series.

Two further distinctions matter: traffic state is based on ROI-filtered observations while the displayed vehicle total can include off-road parked detections; congestion history includes MODERATE samples, not only emitted CONGESTION incidents. Event confidence is a heuristic score, not an evaluated probability. The incident analytics query identifies the camera by a hardcoded camera_name map rather than source_id; renaming a camera can disconnect history. Recorded event timestamps are video seconds and must not be treated as epoch times.

Evidence: [backend/app/operational_analytics.py:1](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:1), [backend/app/database.py:75](/Users/abcd/cityeye-ai/backend/app/database.py:75), [ai/process_video.py:575](/Users/abcd/cityeye-ai/ai/process_video.py:575).

## 13. Citizen system

Backend categories are CONGESTION, ROAD_HAZARD, BLOCKED_ROAD and OTHER. Creation validates description/coordinates/demo_user_id, generates UUID/time and starts PENDING. Matching reports of the **same category** within100m and the previous15min are gathered relative to the new report. At least5 distinct demo_user_id strings changes compatible reports to COMMUNITY_CONFIRMED. That is a local radius/time neighborhood check, not a continuously maintained city clustering engine, verified people, an emergency alert or an AI-verified incident.

The current DB contains0 citizen reports. Creation is public even when product authentication is required; read endpoints require a session and permit Citizen. No authenticated-user link, duplicate-vote anti-abuse mechanism, photo-upload workflow, geographic map provider, submission form or AI incident corroboration is implemented in the current frontend. The page lists at most8 returned reports and explicitly says map/corroboration unavailable. Leaflet/react-leaflet dependencies remain installed but do not make the current placeholder a functional map. The nginx geolocation permission policy is disabled and CSP currently limits image/network sources to self; any future map provider needs explicit product/security integration.

Evidence: [backend/app/database.py:367](/Users/abcd/cityeye-ai/backend/app/database.py:367), [backend/app/schemas.py:31](/Users/abcd/cityeye-ai/backend/app/schemas.py:31), [backend/app/main.py:1068](/Users/abcd/cityeye-ai/backend/app/main.py:1068), [frontend/src/pages/CitizenMapPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/CitizenMapPage.tsx:1), [frontend/nginx.conf:1](/Users/abcd/cityeye-ai/frontend/nginx.conf:1).

## 14. Safe testing and verification audit

Existing suites ran without production database mutation. Backend tests use temporary DBs and an autouse fixture isolates live artifact roots, preventing automatic collectors from importing real camera files. No smoke workflow, production login, generated incident or restore was used to manufacture a green end-to-end result.

| Check | Status | Result | What it proves / limits |
| --- | --- | --- | --- |
| AI | PASS | 220 passed in26.03s | Existing synthetic/unit pipeline, calibration, source adapters, event and trajectory regressions; not real-world recall |
| Backend | FAIL | 247 passed,1 failed in32.62s | Isolated DB/API/auth/live importer/security tests; failure is timeline message expectation |
| Frontend | PASS | 59 passed across5 files in7.38s | jsdom mocked API/component/state tests; not a browser against live DB |
| TypeScript + Vite build | PASS | 62 modules; JS237.24kB gzip74.47kB; CSS46.63kB gzip11.21kB | Current frontend compiles/bundles; outputs only /tmp; package build not invoked verbatim to avoid repo output |
| Python compilation | PASS | 37 files compiled in memory: backend/app14, ai20, scripts3 | Syntax only; no bytecode or application startup |
| Docker running services | PASS | backend/frontend healthy; no backup/live-ai container | These two containers run; NOT a fresh image build or live-camera readiness acceptance |
| Docker rebuild | NOT RUN | No installs/restarts/mutations allowed | Fresh complete deployment NOT VERIFIED |
| Read-only API perimeter | PASS | Health200, anonymous session200/null, six protected API/media surfaces401 | Observed anonymous restrictions; three-role writes covered only isolated tests |
| SQLite snapshot | PASS | mode=ro; quick_check ok; foreign_key_check no violations | Snapshot integrity; not disaster recovery or logical event truth |
| Browser login | PASS | Redirect to /login; rendered at1280×720; console warnings/errors empty | Login loads in current served build |
| Authenticated browser E2E/review writes | NOT RUN | No valid browser session; did not create session/audit writes or click Verify/Dismiss | Fresh live UI review / black-screen path NOT VERIFIED |
| Existing smoke script | NOT RUN | Writes users/reviews; obsolete OPERATOR/REVIEWER fixtures | Not safe for this read-only audit; needs role update/isolation |
| Camera validation | PASS | Limited passive artifact freshness + JPEG scene inspection only | Camera3 presently publishes; no new real positive incident or outage experiment |
| Recorded video assets | PASS | ffprobe input/output metadata; five registered scenarios readable; Maydan annotated frame at30s inspected | Assets and parser outputs exist; full current inference rerun NOT RUN |
| Production restore / load / municipal pilot acceptance | NOT RUN | No production restore, load injection or municipal field trial | Production readiness NOT VERIFIED |

Commands and exact outcomes are in JSON. Backend failure: `test_timeline_returns_real_per_frame_class_counts` expected “Timeline calculated from real YOLO and ByteTrack output.” while source returns the version ending “output with AI traffic state.” HTTP200 and fixture numeric data agree; the suite still **FAILS** and was not edited to hide it. Frontend test names mentioning “real API” use mocked responses and do not demonstrate a live browser/server integration.

The build used existing local TypeScript/Vite binaries, no package install, with output outside the repo. Python source was compiled in memory without `.pyc`. Docker health checks were read, not rebuilt. `scripts/smoke_test.py` is NOT RUN because it logs in, creates users and changes real review status; it also still creates rejected legacy OPERATOR/REVIEWER roles. Historical camera/source/review reports are distinguished from tests executed today. There is no verified current production-browser E2E runner passing all roles/pages against the deployed stack.

Evidence: [backend/tests/conftest.py:1](/Users/abcd/cityeye-ai/backend/tests/conftest.py:1), [backend/tests/test_analysis_api.py:70](/Users/abcd/cityeye-ai/backend/tests/test_analysis_api.py:70), [scripts/smoke_test.py:140](/Users/abcd/cityeye-ai/scripts/smoke_test.py:140), [frontend/src/App.test.tsx:1](/Users/abcd/cityeye-ai/frontend/src/App.test.tsx:1), [frontend/vite.config.ts:1](/Users/abcd/cityeye-ai/frontend/vite.config.ts:1).

## 15. Performance and scaling

This audit did not run a load benchmark. Existing measurements and current observations have different scopes:

- **Current Camera3 point sample:**3.2AI FPS,8.628capture FPS,8.217preview-publication FPS, generation116 and851 reconnect attempts at the first read. Configured caps5AI/12preview are targets, not achieved throughput. Later snapshots can differ.
- **Historical live DB average:** approximately3.68AI FPS and11.75capture FPS across~2329 stored samples; this is an average of sampled reported rates, **not** full-time uptime, p95 latency or concurrent-camera capacity.
- **Current Docker snapshot:** backend0.16%CPU/88.46MiB, nginx0%CPU/7.441MiB. These exclude the host AI/VLC process and do not measure total application cost. No current host AI CPU/RAM benchmark was taken.
- **Archived detector-only evaluation:** normal/congestion YOLOv8n about9.2FPS, alternative YOLOv8s about4.6FPS on a few warmed-up frames, excluding decode/tracker/drawing/encoding. These Sep10 measurements cannot be used as current full-stack throughput. Host dependency/runtime changes further limit comparability.
- **Archived source adapter diagnostic:** an older direct-VLC30-frame sample reported~11decoded FPS/~135MB peakRSS/4.7ms maximum frame age. That was a different callback path and short source test, **not present sensor-to-browser latency**.
- JPEG publication is separate from inference; current runtime encoding latency/p95 end-to-end delay/network bandwidth is **NOT VERIFIED**. Quality75/95 settings and file sizes alone do not constitute latency measurements.
- Most live product reads poll every2s; analytics collection every5s stores at most1/min; source freshness can expire independent of polling. Multi-viewer MJPEG uses a synchronous per-stream iterator and repeated filesystem checks, so scaling needs measurement.
- Local assets occupy hundreds ofMiB; no growth/retention forecast is asserted. API lists/CSV parsing and retained event JSON are unbounded enough to require later profiling.

**1 camera:** functional host evidence, limited daytime validation, no availability SLA. **10 cameras:** NOT VERIFIED. **50 cameras:** NOT VERIFIED. **100 cameras:** NOT VERIFIED. No linear extrapolation is justified from one camera and detector-only frame benchmarks. Cross-camera analytics/re-ID is not implemented even though per-camera directory/API plumbing exists.

Evidence: timestamped JSON runtime/DB snapshots; [ai/EVALUATION_REPORT.md:74](/Users/abcd/cityeye-ai/ai/EVALUATION_REPORT.md:74), [ai/RTSP_PILOT_REPORT.md:84](/Users/abcd/cityeye-ai/ai/RTSP_PILOT_REPORT.md:84), [ai/process_video.py:372](/Users/abcd/cityeye-ai/ai/process_video.py:372), [backend/app/live_camera.py:123](/Users/abcd/cityeye-ai/backend/app/live_camera.py:123).

## 16. Current known limitations and findings

Priorities reflect consequence and evidence, not numerical project scores. CODE-PATH VERIFIED means a branch is deterministically unsafe from inspected code, but was not triggered against production. NOT VERIFIED is retained for real-world causal/operational claims. No fixes were applied.

| ID / priority | Finding | Evidence basis | Impact | Evidence | Next action |
| --- | --- | --- | --- | --- | --- |
| I01 P0 | Genuine stopped-event positive acceptance is still missing | HISTORICAL EVIDENCE + CURRENT CODE | Core promised event has not passed a natural moved→stop→8s→incident chain. | [diagnostics/camera3-stopped-validation/validation-report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-stopped-validation/validation-report.md:1) | Capture a natural eligible daytime sequence; label recorded alternatives honestly |
| I02 P0 | Daylight calibration stays enabled without an automatic condition gate | CODE + HISTORICAL CAMERA EVIDENCE | Night quality is poor in historical evidence; NORMAL can still be computed despite unsuitable visibility. | [ai/config/live_camera.json:158](/Users/abcd/cityeye-ai/ai/config/live_camera.json:158); [ai/calibration.py:104](/Users/abcd/cityeye-ai/ai/calibration.py:104) | Enforce documented operator night-disable procedure; separately design quality gating |
| I03 P0 | Recorded review failure can appear successful in the Command Center dialog | CODE-PATH VERIFIED; failed-write UI not executed | useEvents catches request failure and resolves; caller unconditionally writes VERIFIED/DISMISSED into selected dialog. DB may remain PROPOSED. Live review has try/finally without catch and no dedicated action-error state. | [frontend/src/hooks/useEvents.ts:44](/Users/abcd/cityeye-ai/frontend/src/hooks/useEvents.ts:44); [frontend/src/pages/MunicipalDashboard.tsx:546](/Users/abcd/cityeye-ai/frontend/src/pages/MunicipalDashboard.tsx:546) | Propagate success/failure, update dialog only from confirmed backend response; add failure regression |
| I04 P0 | Recorded zero-detection frames disappear from API timeline | CURRENT ASSET COUNTS + CODE | Rain: 787 processed traffic frames vs 611 detection frames; 176 gaps. Selection carries previous frame counts through gaps. | [backend/app/analysis.py:247](/Users/abcd/cityeye-ai/backend/app/analysis.py:247); [frontend/src/pages/MunicipalDashboard.tsx:319](/Users/abcd/cityeye-ai/frontend/src/pages/MunicipalDashboard.tsx:319) | Join full processed frame timeline, preserve explicit zero counts; test playback gaps |
| I05 P0 | Backend suite is not green | EXECUTED TEST | One exact message contract mismatch: 247 pass / 1 fail; numeric fixture fields agree. | [backend/tests/test_analysis_api.py:70](/Users/abcd/cityeye-ai/backend/tests/test_analysis_api.py:70); [backend/app/analysis.py:354](/Users/abcd/cityeye-ai/backend/app/analysis.py:354) | Decide intended message contract and align implementation/test in separate task |
| I06 P1 | Smoke test uses removed roles and mutates real state | CODE VERIFIED; NOT RUN | OPERATOR/REVIEWER user creation is incompatible with ADMIN/EMPLOYEE/CITIZEN; test creates users and reviews incidents. | [scripts/smoke_test.py:151](/Users/abcd/cityeye-ai/scripts/smoke_test.py:151); [backend/app/main.py:125](/Users/abcd/cityeye-ai/backend/app/main.py:125) | Update role fixtures and isolate smoke DB/artifacts before execution |
| I07 P1 | Scheduled backup service is not deployed | RUNTIME OBSERVED | Only old manual DB copies found; no backup volume in current Docker inventory. Evidence remains a separate unprotected asset. | [compose.yaml:68](/Users/abcd/cityeye-ai/compose.yaml:68); [backend/app/backups.py:1](/Users/abcd/cityeye-ai/backend/app/backups.py:1) | Enable verified backup plus media/config recovery drill in follow-up |
| I08 P1 | CityEye is running a demo HTTP deployment, not production perimeter | RUNTIME + CODE | Ports bind all interfaces; no TLS termination in audited stack; no login throttling/MFA. External firewall exposure NOT VERIFIED. | [compose.yaml:9](/Users/abcd/cityeye-ai/compose.yaml:9); [frontend/nginx.conf:1](/Users/abcd/cityeye-ai/frontend/nginx.conf:1) | Establish restricted deployment, HTTPS, access policy and abuse protections before pilot exposure |
| I09 P1 | Citizen confirmation is spoofable demo consensus | CODE VERIFIED | Public POST trusts demo_user_id; five different client strings are not five verified people. | [backend/app/main.py:1068](/Users/abcd/cityeye-ai/backend/app/main.py:1068); [backend/app/database.py:388](/Users/abcd/cityeye-ai/backend/app/database.py:388) | Do not operationalize COMMUNITY_CONFIRMED until identity/abuse controls exist |
| I10 P1 | Recorded provenance and source identity are incomplete | DB + CODE | Congestion DB row has null source identity; recorded UUIDs/filenames can change on rerun, and old DB rows may disappear from Incidents if absent from current artifacts. | [backend/app/main.py:937](/Users/abcd/cityeye-ai/backend/app/main.py:937); [backend/app/scenarios.py:1](/Users/abcd/cityeye-ai/backend/app/scenarios.py:1) | Persist scenario identity and immutable run/model/config/media provenance |
| I11 P1 | Analytics counts and timestamps need careful interpretation | CODE VERIFIED | Incident join uses camera_name instead of source_id; MODERATE counts as congestion; chart equal-spaces buckets even across missing hours. | [backend/app/operational_analytics.py:138](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:138); [frontend/src/pages/AnalyticsPage.tsx:32](/Users/abcd/cityeye-ai/frontend/src/pages/AnalyticsPage.tsx:32) | Use explicit identity/time semantics and show gaps/coverage |
| I12 P1 | Maydan integration is playback-ready, not road-calibrated | CURRENT CONFIG + VISUAL FRAME | Coordinates are 0,0; polygon covers almost whole image including non-road; direction is generic and event thresholds restrictive. No approval evidence found. | [ai/config/scenarios/maydan_palestine.json:1](/Users/abcd/cityeye-ai/ai/config/scenarios/maydan_palestine.json:1) | Validate actual site and lane/road geometry before event claims |
| I13 P1 | Existing stopped output is historical, not a current positive regression | ASSET + DB + FFPROBE | PROPOSED artifact is the labeled pre-fix false event; DB correctly DISMISSED. Source video is 1920×1080 while annotated output is 1280×720; run lineage unverified. | [ai/scenario_outputs/stopped_vehicle/events.json:1](/Users/abcd/cityeye-ai/ai/scenario_outputs/stopped_vehicle/events.json:1); [diagnostics/camera3-stopped-validation/validation-report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-stopped-validation/validation-report.md:1) | Preserve false-positive example, add a distinct genuine positive recording/run manifest |
| I14 P1 | Unprofiled cameras retain legacy geometry | CODE VERIFIED | Camera3 is guarded; camera5/7 have no profile, so resolver returns None and shared generic geometry remains available if workers reenabled. | [ai/calibration.py:98](/Users/abcd/cityeye-ai/ai/calibration.py:98); [ai/config/live_camera.json:43](/Users/abcd/cityeye-ai/ai/config/live_camera.json:43) | Require per-camera approval before activating other streams |
| I15 P1 | Repeated reconnects and limited observability prevent reliability claims | RUNTIME SNAPSHOT | Snapshot showed 851 reconnect attempts and generation116, but no dependable denominator/uptime SLA; physical cause NOT VERIFIED. | [ai/frame_source.py:981](/Users/abcd/cityeye-ai/ai/frame_source.py:981); [ai/live_output/camera-3/camera_status.json:1](/Users/abcd/cityeye-ai/ai/live_output/camera-3/camera_status.json:1) | Run a timestamped soak with outage/latency/quality annotations |
| I16 P2 | Raw MJPEG freshness and retry recovery are weaker than AI metrics | CODE VERIFIED | Preview checks health at open only; successful image load does not reset retryToken; after accumulated retries a later failure can jump to ERROR. | [backend/app/main.py:838](/Users/abcd/cityeye-ai/backend/app/main.py:838); [frontend/src/components/LiveMjpegImage.tsx:72](/Users/abcd/cityeye-ai/frontend/src/components/LiveMjpegImage.tsx:72) | Exercise intermittent stream recovery and reset per-failure retry budget |
| I17 P2 | Several frontend pages have stale/error/empty-state ambiguities | CODE VERIFIED | Camera fetch error becomes no cameras; Incidents/Citizen can initially show empty before fetch; recorded incident lists do not poll in Incidents; analytics refreshes only on filter/retry. | [frontend/src/pages/CamerasPage.tsx:85](/Users/abcd/cityeye-ai/frontend/src/pages/CamerasPage.tsx:85); [frontend/src/pages/IncidentsPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/IncidentsPage.tsx:1); [frontend/src/pages/CitizenMapPage.tsx:1](/Users/abcd/cityeye-ai/frontend/src/pages/CitizenMapPage.tsx:1) | Add explicit load/failure/freshness states and recheck after external reviews |
| I18 P2 | Review detail presentation/accessibility needs cleanup | CODE VERIFIED; full viewport audit NOT VERIFIED | Verified/dismissed details still say requires verification; stale Reviewer wording; no dialog Escape/focus trap or image-failure fallback. | [frontend/src/components/Incident.tsx:57](/Users/abcd/cityeye-ai/frontend/src/components/Incident.tsx:57) | Improve review state labels and accessible error handling |
| I19 P1 | Data lifetime and scale are not bounded | CODE VERIFIED | All events/lists and recorded CSV parsed eagerly; no runtime observation/evidence retention; JSON delivery list grows; SQLite/filesystem single-host architecture. | [backend/app/database.py:322](/Users/abcd/cityeye-ai/backend/app/database.py:322); [ai/event_pipeline.py:208](/Users/abcd/cityeye-ai/ai/event_pipeline.py:208); [backend/app/analysis.py:49](/Users/abcd/cityeye-ai/backend/app/analysis.py:49) | Define retention/pagination/archival after measuring one-camera workload |
| I20 P1 | Safety gate has an unhandled uncalibrated-bicycle path | CODE-PATH VERIFIED; no live trigger observed | When calibration disables congestion, bicycle_in_road is None, then int(None) raises if an accepted bicycle exists. Camera3 disable/resolution-mismatch conditions can hit this path. | [ai/process_video.py:997](/Users/abcd/cityeye-ai/ai/process_video.py:997) | Add isolated regression and null-safe road-membership handling in follow-up |
| I21 P2 | Historical documentation contradicts current implementation | DOCUMENT CONTRADICTION | Map/no-auth/I420/stopped-positive claims are obsolete; roadmap must use current source and explicit evidence scope. | [README.md:222](/Users/abcd/cityeye-ai/README.md:222); [ai/PILOT_READINESS_REPORT.md:1](/Users/abcd/cityeye-ai/ai/PILOT_READINESS_REPORT.md:1); [ai/RTSP_PILOT_REPORT.md:1](/Users/abcd/cityeye-ai/ai/RTSP_PILOT_REPORT.md:1) | Make this master reference authoritative, then align older docs separately |
| I22 P1 | Local/ignored asset dependencies limit reproducibility | FILES + INSTALLED VERSIONS | Scenario configs/videos/outputs/weights ignored; host NumPy2.5.2 differs from runtime pin2.4.6; host service uses absolute user paths. | [.gitignore:1](/Users/abcd/cityeye-ai/.gitignore:1); [scripts/launchd/com.cityeye.camera3.plist:1](/Users/abcd/cityeye-ai/scripts/launchd/com.cityeye.camera3.plist:1); [ai/requirements.runtime.txt:1](/Users/abcd/cityeye-ai/ai/requirements.runtime.txt:1) | Record a portable asset manifest, versions and deployment procedure |

Additional domain limits: generic COCO detection is not guaranteed on small/occluded/edge-cropped vehicles; night glare/veil can make source detail unusable; movement is image-space and sensitive to box jitter/perspective; identity can reset on outages; approved geometry covers only part of the roadway; rule scores are not calibrated probabilities; synthetic tests do not measure false negatives. There is no weather detector merely because rainy footage exists, no LPR, physical speed measurement or automatic enforcement. Recorded outputs may be stale relative to current code. SQLite plus files is a single-host persistence design without verified failover. No paid customer, pilot SLA, municipal dispatch workflow or production acceptance evidence exists in the audited materials.

The disabled-calibration bicycle finding (I20) deserves a precise boundary: `bicycle_in_road` becomes None when `congestion_rule` is absent, then `int(bicycle_in_road)` raises. This affects an accepted bicycle in an uncalibrated/disabled-road state; no such live occurrence was observed here. It does **not** mean Camera3 currently crashes continuously. The current220 AI tests pass despite this uncovered branch.

## 17. CURRENT HACKATHON DEMO READINESS

| Category | Item | Honest scope / reason |
| --- | --- | --- |
| SAFE TO DEMO | Recorded normal/congestion/Maydan detection + track playback | Rehearsed existing H.264 assets; show RECORDED explicitly; no claim inference is newly running in browser; mention rain timeline issue if using rain |
| SAFE TO DEMO | Existing incident evidence and stored decisions | View actual evidence/history; explain old wrong-way and dismissed bbox-jitter stop correctly; do not count them as valid Camera3 positives |
| SAFE TO DEMO | Authentication/role concept in a prepared demo environment | Current code/tests enforce3roles; use predefined accounts and rehearse in a separate writable acceptance task |
| SAFE TO DEMO | Sample-based historical analytics | Explain counts are repeated frame observations, not vehicles passed or forecast; show collection gaps |
| RISKY TO DEMO | Live Camera3 | Daylight/quality/network dependent; repeated reconnects and current scene may have no vehicles; recorded fallback required |
| RISKY TO DEMO | Live Verify/Dismiss without rehearsal | Backend and positive mocks work, historical review exists; failed recorded dialog path misleading, current live browser acceptance not done |
| RISKY TO DEMO | Rainy clip synchronized counters | 176 processed zero-detection frames absent from current timeline; old counts may persist |
| RISKY TO DEMO | Maydan incidents or site location | Broad unvalidated geometry and0,0coordinates; no event evidence |
| DO NOT DEMO | Camera3 reliable Stopped Vehicle/Wrong Way/Road Blockage | Natural positive stop not validated; other rules intentionally disabled |
| DO NOT DEMO | Functional Citizen Map or AI citizen corroboration | Current page explicitly placeholder; no integration |
| DO NOT DEMO | Prediction, LPR, speed enforcement, 10–100camera capacity | Not implemented or not measured |
| DO NOT DEMO | Production municipal readiness / guaranteed accuracy / automatic dispatch | No supporting operational, security, accuracy or acceptance evidence |

Recommended controlled presentation: prepared sign-in → choose a clearly labeled recorded normal or Maydan clip → point out real boxes/IDs and sampled counts → inspect a genuine recorded congestion evidence image → explain human review → show analytics with sampling caveats. Use the dismissed stopped false proposal to demonstrate why review matters, not as a successful stopped detector. Do not operate live calibrated road rules at night without the documented manual condition control. This is a demo plan, not evidence that every step was rerun in this read-only audit.

## 18. History and contradictions

Git dates below come from local history, not reconstructed memories. Uncommitted features have file/diagnostic evidence but no invented commit date.

| Evidence date | Phase | Evidence |
| --- | --- | --- |
| 2026-08-20 | Initial two-week scaffold and YOLO detect/track slice | c93162b |
| 2026-08-24 | Trajectory, event contract, wrong-way/stopped/congestion and evidence | a958617,09298a2,2d617e7,251e94c,6664fc9,ddc2fc8 |
| 2026-08-25 | FastAPI/SQLite/event/evidence APIs; citizen reports/clustering; dashboard and recorded integration | f8869f8,15a56c7,c492586,8866b95,95beea0,7fc7d98,e74f9b0 |
| 2026-09-04–05 | Dashboard layout; traffic detection, person and bicycle metrics | 978506a,7e2dcd0,d1460b4,47f61d0 |
| 2026-09-13–14 | Containers/env/health/backup/security/auth/audit | 3a060ec,bf3b8fd,3c90d7b,6351fb7,b3502d9,9d3e9bd |
| 2026-09-15 | Command Center and Road Blockage | 4176470 |
| 2026-09-17 | Resilient capture and real analytics baseline merge | fce92ab,5db6adc,d9be07f |
| 2026-09-18 diagnostic timestamps | Daylight quality/calibration and stopped negative-regression investigation | diagnostics/camera3-diagnostic, camera3-calibration-day, camera3-stopped-validation |
| Current uncommitted tree; Sep21/22 file mtimes are not commits | Three-role RBAC, login visual, Maydan registry/assets, timeline traffic-state integration, live truth/importer changes | Current source/dirty status and scenario assets; exact implementation chronology beyond recorded evidence NOT VERIFIED |
| 2026-09-24 | This read-only reconstruction | Current report/JSON + executed checks |

| Older claim | Contradicting current evidence | Resolution |
| --- | --- | --- |
| README: Leaflet citizen map implemented | CitizenMapPage renders NOT YET AVAILABLE, no geographic layer | Current source wins: PLACEHOLDER; dependency presence not feature completion |
| RTSP pilot report: no authentication | Current auth middleware/role tests/runtime auth_required=true | Obsolete security description |
| RTSP pilot report: macOS direct I420 callback;944×1090 | Current macOS factory selects VLCLocalBridgeCapture; current profile/JPEG944×1080 | Different pipeline stage/version; do not diagnose current path using old callback assumptions |
| Pilot readiness: stopped clip validated, no P0 for demo | Sep18 diagnostic proves pre-existing parked false positive; post-fix0events; DB DISMISSED | Old positive claim superseded; genuine positive acceptance still missing |
| Sep10 evaluation: stopped threshold80px/s and no structured event details | Current normalized thresholds/prior-motion gate and structured event details exist | Useful historical benchmark only; current rule/config/contract supersede |
| Older setup: four scenarios | SCENARIOS now includes maydan_palestine and local output exists | Five registered scenarios now |
| Old role names OPERATOR/REVIEWER | Current schema/admin UI only ADMIN/EMPLOYEE/CITIZEN | Legacy docs and smoke fixtures must be updated |
| Healthy/READY means operationally validated | Readiness checks DB; calibration READY means geometry accepted, not positive event proof | Separate service health, rule enabled status and real acceptance |
| VERIFIED means algorithm scientifically validated | Old wrong-way DB row reviewed before correct direction calibration; source report warns not proof | Human database decision and ground-truth model validation are different |

Evidence: `git log --reverse --format='%h %ad %s' --date=short` captured in JSON; [README.md:222](/Users/abcd/cityeye-ai/README.md:222); [ai/RTSP_PILOT_REPORT.md:1](/Users/abcd/cityeye-ai/ai/RTSP_PILOT_REPORT.md:1); [ai/PILOT_READINESS_REPORT.md:1](/Users/abcd/cityeye-ai/ai/PILOT_READINESS_REPORT.md:1); [diagnostics/camera3-stopped-validation/validation-report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-stopped-validation/validation-report.md:1); [backend/app/scenarios.py:1](/Users/abcd/cityeye-ai/backend/app/scenarios.py:1).

## 19. Evidence-backed lessons

1. **Source conditions matter before model tuning.** The same Camera3 path produced useful daytime detections and badly veiled older nighttime imagery. This supports investigating native source quality before changing thresholds. [diagnostics/camera3-diagnostic/report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-diagnostic/report.md:1).
2. **Detection is not event correctness.** The stopped clip had real boxes and a real JPEG but false physical prior motion from box jitter; a complete persistence path can faithfully store a wrong proposal. [diagnostics/camera3-stopped-validation/validation-report.md:1](/Users/abcd/cityeye-ai/diagnostics/camera3-stopped-validation/validation-report.md:1).
3. **Calibration must bind to the camera and observed image.** Generic polygons/direction yielded misleading old results; the current Camera3 profile validates identity/resolution and disables unknown direction. Same-size reposition/lighting still needs operator attention. [ai/calibration.py:1](/Users/abcd/cityeye-ai/ai/calibration.py:1).
4. **Human review needs truthful acknowledgment.** The DB can transact a decision/audit correctly while frontend failure handling mislabels the result. Review is part of the product, not decoration. [backend/app/database.py:279](/Users/abcd/cityeye-ai/backend/app/database.py:279), [frontend/src/pages/MunicipalDashboard.tsx:546](/Users/abcd/cityeye-ai/frontend/src/pages/MunicipalDashboard.tsx:546).
5. **Time/source provenance is essential.** Recorded seconds and live Unix time have different meanings; source-null rows and regenerated evidence names make history fragile. [backend/app/main.py:937](/Users/abcd/cityeye-ai/backend/app/main.py:937), [ai/event_pipeline.py:266](/Users/abcd/cityeye-ai/ai/event_pipeline.py:266).
6. **Counts must retain zero and missing semantics.** Real CSV numbers are still misleading when missing frames carry earlier values or sparse observations are described as throughput. [backend/app/analysis.py:247](/Users/abcd/cityeye-ai/backend/app/analysis.py:247), [backend/app/operational_analytics.py:1](/Users/abcd/cityeye-ai/backend/app/operational_analytics.py:1).
7. **Implemented operations are not deployed operations.** A tested backup worker and Compose service exist, but no running backup service/volume was observed. Current runtime must be checked independently of docs. [compose.yaml:68](/Users/abcd/cityeye-ai/compose.yaml:68).

## 20. Gaps between this MVP and a municipal product

| Domain | Evidence-backed gap | Required outcome |
| --- | --- | --- |
| TECHNICAL | Single-host files/SQLite, unbounded histories, host-specific paths (I19,I22) | Reproducible deployment and bounded recoverable state |
| AI | No natural stopped positive, limited night/occlusion quality, no labeled recall (I01,I02) | Camera-condition-specific acceptance and error measurements |
| DATA | No immutable run provenance; source-null rows; sparse history (I10,I13) | Traceable model/config/media/event identities and coverage |
| PRODUCT | Verify/Dismiss only; no assignment/dispatch/closure workflow | Agreed operator response journey and acceptance criteria |
| FRONTEND | Review failure and frame-gap truth bugs; map placeholder (I03,I04,I17) | Reliable evidence/action feedback before extra visuals |
| BACKEND | One test failure; lazy recorded persistence; unpaginated APIs (I05,I10,I19) | Stable contracts and durable source-scoped history |
| SECURITY | HTTP demo perimeter, no rate/MFA/recovery; spoofable citizen IDs (I08,I09) | Pilot access/abuse policy enforced and verified |
| DEPLOYMENT | Two services active, host AI separate; backup inactive (I07,I22) | Portable secure install with measured health/recovery |
| OPERATIONS | No verified soak SLA, night guard automated policy or full restore (I02,I07,I15) | Operator runbook, monitoring, backup evidence and incident ownership |
| BUSINESS | No verified buyer/pilot contract/measured value in repo | Municipal discovery and scoped pilot success criteria after technical truth is stable |

## 21. What should be built next

These are follow-up recommendations only; none was implemented during this audit. Evidence IDs refer to section16.

| Priority | Problem | Why it matters | Evidence | Expected outcome | Dependencies | Next work |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | Positive stopped-vehicle proof absent | Central event promise still unproven | I01, I13 | One genuine moved→ROI→stop duration→one proposal→evidence→DB→review trail, with pre-existing parked negative control | Suitable daylight footage, current calibration; separate writable validation task | Obtain and annotate eligible footage before tuning models |
| P0 | Review UI can claim a failed decision succeeded | Human trust requires DB-confirmed review | I03 | Failed write remains PROPOSED with actionable error; no stale overwrite | Minimal frontend change + regression tests | Fix review result propagation and error states |
| P0 | Recorded zero frames carry old counts | Demo numbers must describe visible frame | I04 | Every processed frame has explicit zero/unknown data and synchronized display | Full per-frame metadata + frontend regression | Fix timeline gap semantics |
| P0 | Invalid/night calibration conditions not safely represented everywhere | Daylight-only scope and safe-disabled handling are operational requirements | I02, I20 | Documented daylight run discipline now; null-safe disabled-rule processing and tested condition gate later | Appropriate bicycle/uncalibrated regression and night-quality evidence | Keep manual night restriction; fix int(None) path in separate scoped task |
| P0 | Current backend tests fail | Cannot honestly release with known contract regression | I05 | Intentional stable timeline response contract and green suite | Agree message contract | Resolve exact message mismatch without unrelated refactor |
| P1 | Acceptance tooling and artifact lineage stale | Team cannot reproduce one trustworthy build/scenario | I06, I10, I13, I22 | Isolated modern-role smoke; model/config/source hashes; explicit recorded source IDs | Stable P0 logic and portable asset bundle | Repair smoke fixtures and add run manifests |
| P1 | Backup/recovery and production perimeter not operational | Pilot data/security cannot rely on local demo defaults | I07, I08, I09 | Verified DB+evidence restore, restricted HTTPS, rate/abuse controls | Deployment owner, storage/TLS/access decisions | Harden a defined pilot installation before external exposure |
| P1 | Live reliability and event precision unmeasured | 851 attempts and sparse samples do not establish service quality | I01, I14, I15 | Labeled one-camera day/night corpus, soak report, error budgets and outage behavior | Legal source access, controlled observation conditions | Measure one camera before scaling |
| P1 | Maydan geometry/location unvalidated | Playing an MP4 is not calibrated incident monitoring | I12 | Verified site identity and road regions; uncertain rules left disabled | Reference footage and lawful direction evidence | Run a separate scene calibration task |
| P2 | Freshness/analytics/history UI defects | Operators need honest gaps and robust recovery | I11, I16, I17, I18 | Clear loading/errors, time-scaled gaps, robust reconnect, accessible review dialog | P0 truth/review fixes | Improve operational UI semantics |
| P2 | Unbounded storage/list processing | Continuous operation grows files/DB/response cost | I19 | Measured retention, pagination and archived immutable evidence | Data retention policy and one-camera workload measurements | Bound data lifetimes and API page sizes |
| LATER | Vision features outrun validated core | No evidence yet supports forecasting, LPR or large camera fleet | I01, I12, I15 | Only add feature after suitable data, validated core and explicit municipal need | Validated single-camera pilot + stakeholder acceptance | Defer forecasting, cross-camera re-ID, LPR and full citizen platform |

## 22. What should not be built yet

- **Traffic prediction:** sparse samples are not unique flow ground truth and no validated baseline exists; first make observation semantics/coverage trustworthy.
- **LPR/ANPR or speed enforcement:** current road-user detector and scene evidence do not establish plate readability, calibrated distance or legal operational suitability.
- **10–100 camera rollout/cross-camera re-ID:** one-camera reliability, source-specific geometry and deployment recovery are not yet established.
- **More incident classes:** current stopped positive acceptance is missing and review feedback has a concrete bug; expanding event types multiplies unvalidated behavior.
- **A full citizen platform/AI corroboration:** current map is absent and confirmation trusts demo identities; first decide an authenticated, abuse-resistant, operational use case.
- **Another detector solely for more boxes:** historical alternate-model runs did not measure true-positive recall and cost more compute. First annotate the actual failure cases.
- **More cosmetic dashboard complexity:** recorded zero-frame counts and false review acknowledgment directly undermine trust; resolve them before presentation expansion.

Evidence: I01–I04,I09,I12,I15,I22; ai/EVALUATION_REPORT.md ground-truth limitations; current feature matrix.

## 23. Business/product interpretation without market research

**Who might pay:** a municipality, traffic authority or contractor operating traffic surveillance; this is the intended customer hypothesis from project language, not a confirmed customer. **Who uses it:** municipal operator/reviewer, administrator and a limited citizen-facing role. **Who benefits if it works:** road users/residents and staff who can inspect focused evidence instead of uninterrupted video. No benefit magnitude is established.

A municipality would be buying a supported monitoring-and-review workflow attached to its cameras: validated scene-specific observations, dependable proposed incidents, inspectable evidence, accountable review and operational continuity. Buying “YOLO detection” alone does not satisfy that workflow. The project has no verified pricing, revenue, subscription management, procurement fit, customer interview, deployment contract or measured staff-time savings in the inspected materials.

**Classification:** a functioning **controlled-demo MVP / engineering prototype** with a narrow live-camera trial foundation. It is not yet a generally pilot-ready unattended deployment: a supervised engineering trial is plausible only with explicit daylight/geometry/rule boundaries, recovery/security plans and honest acceptance criteria. **Production-ready: NO evidence establishing this.** This classification follows the current event-validation gap, inactive backups, demo perimeter and frontend truth defects, not an arbitrary maturity score.

Evidence: [README.md:1](/Users/abcd/cityeye-ai/README.md:1), feature matrix, I01–I15, current runtime snapshot. No market research was performed and no customers/deployments were invented.

## 24. Master feature matrix

“Partial” real-world validation is explicitly bounded; it never means municipal deployment approval. No feature receives an unqualified production-ready claim.

| Feature | Implemented? | Tested? | Real-world validated? | Demo-ready? | Production-ready? | Dependencies | Known limitations | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Vehicle detection/classification | IMPLEMENTED BUT PARTIAL | Controlled tests | Limited Camera 3 daylight + recorded artifacts | YES, limited scenes | NOT VERIFIED | yolov8n.pt; decoded image | No labeled municipal precision/recall; misses and classification errors remain | Annotate representative day/night frames |
| Person and bicycle detection | IMPLEMENTED BUT PARTIAL | Controlled tests | Recorded outputs exist; class accuracy NOT VERIFIED | Counts only | NOT VERIFIED | Existing stack | No independent person-in-road incident; no real accuracy study | Validate scoped acceptance |
| ByteTrack identities | IMPLEMENTED BUT PARTIAL | Controlled tests | Limited successive Camera 3 daylight frames | YES, scoped | NOT VERIFIED | Existing stack | No cross-camera identity; no ID-switch benchmark | Evaluate ID continuity on labeled motion/occlusion footage |
| Movement/trajectory state | IMPLEMENTED BUT NOT VALIDATED | Controlled tests | Moving live tracks; genuine moved-to-stop NOT VERIFIED | Conditional | NOT VERIFIED | Existing stack | Image-space movement is not road speed; physical stop causality incomplete | Capture a genuine sustained movement-to-stop episode |
| Recorded video integration | IMPLEMENTED | Controlled tests | Actual video assets inspected | YES, rehearsed | NOT VERIFIED | Ignored local MP4/config/output files | Precomputed playback; no upload/job management UI; provenance manifests missing | Validate scoped acceptance |
| Maydan Palestine | IMPLEMENTED BUT PARTIAL | Controlled tests | Annotated frame at 30s inspected; no event/geometry validation | Detection/tracking playback only | NOT VERIFIED | Existing stack | Coordinates 0,0; broad ROI/global vector unvalidated; zero incident artifacts | Validate scene-specific geometry and location separately |
| RTSP/DVR ingestion | IMPLEMENTED BUT PARTIAL | Controlled tests | Camera 3 current ONLINE artifacts | Conditional daylight | NOT VERIFIED | Host Python/VLC; DVR/network | Single selected camera evidence; repeated reconnects; long outage reliability unmeasured | Validate scoped acceptance |
| JPEG/MJPEG preview and AI view | IMPLEMENTED BUT PARTIAL | Controlled tests | Camera 3 JPEG visually inspected; historical matched-source diagnostic | Conditional | NOT VERIFIED | Existing stack | Raw stream lacks in-stream freshness callback; UI retry budget not reset on load | Validate scoped acceptance |
| Live freshness/generation truth | IMPLEMENTED | Controlled tests | Fresh changing production snapshots; outages covered by tests | YES | NOT VERIFIED | Existing stack | Frame/JSON publications not one transaction; not a network-latency guarantee | Validate scoped acceptance |
| Camera 3 road/stopped calibration | IMPLEMENTED BUT PARTIAL | Controlled tests | Road inclusion/exclusion demonstrated Sep18 | Daylight roadway overlay/limited counts | NOT VERIFIED | Existing stack | Daylight-only manual night guard; incomplete roadway coverage; positive event acceptance missing | Retain daylight restriction and validate positive stop |
| Stopped Vehicle event | IMPLEMENTED BUT NOT VALIDATED | Controlled tests | NOT VALIDATED; recorded positive acceptance FAIL | Negative regression/reviewer dismissal only | NOT VERIFIED | Existing stack | No genuine Camera 3 positive; current demo event is documented pre-fix false proposal | Obtain real moved-then-stopped footage meeting configured duration |
| Wrong Way event | IMPLEMENTED BUT NOT VALIDATED | Controlled tests | NOT VALIDATED; old VERIFIED DB row is not valid calibration proof | DO NOT DEMO as reliable live detection | NOT VERIFIED | Existing stack | Camera 3 direction disabled; no legally direction-labeled positive clip | Validate scoped acceptance |
| Congestion event/state | IMPLEMENTED BUT PARTIAL | Controlled tests | Recorded scenario evidence; Camera 3 positive NOT VALIDATED | Recorded congestion with caveat | NOT VERIFIED | Existing stack | Live sensitivity not calibrated by positives; dense moving traffic can satisfy high-count branch | Validate scoped acceptance |
| Road Blockage event | IMPLEMENTED BUT NOT VALIDATED | Controlled tests | NOT VERIFIED | Synthetic rule demonstration only | NOT VERIFIED | Existing stack | Camera 3 deliberately disabled; real blocked-lane positive missing | Validate scoped acceptance |
| Person-in-road incident | NOT IMPLEMENTED | Membership tests only | NOT VERIFIED | DO NOT present as incident detection | NOT VERIFIED | Existing stack | No event enum/rule/persistence lifecycle for this incident | Validate scoped acceptance |
| Evidence generation/serving | IMPLEMENTED BUT PARTIAL | Controlled tests | Existing DB evidence files present | YES | NOT VERIFIED | Existing stack | Files outside DB backups; recorded names can be overwritten by reruns | Validate scoped acceptance |
| Live incident persistence/replay | IMPLEMENTED | Controlled tests | One historical Camera 3 row; new valid positive incident NOT VERIFIED | Existing history only | NOT VERIFIED | Existing stack | Physical episode dedupe across worker restarts not guaranteed; unbounded history | Validate scoped acceptance |
| Recorded incident persistence | IMPLEMENTED BUT PARTIAL | Controlled tests | Recorded verified congestion + dismissed false-stop DB rows | YES with labels | NOT VERIFIED | Existing stack | Unreviewed artifacts not automatically DB-persisted; source identity may be null | Validate scoped acceptance |
| Human review/audit | IMPLEMENTED BUT PARTIAL | Controlled tests | Historical View/Dismiss proof and DB audit rows; fresh browser write NOT RUN | Rehearse successful path; errors risky | NOT VERIFIED | Existing stack | Command Center failure handling can misstate local review; no assignment/dispatch lifecycle | Validate scoped acceptance |
| Operational analytics | IMPLEMENTED BUT PARTIAL | Controlled tests | 2329 production samples at saved DB snapshot | YES with metric definitions | NOT VERIFIED | Existing stack | Not throughput; sparse samples; chart gap distortion; camera-name incident join | Fix time-gap display and specify confidence/coverage semantics |
| Citizen report API/storage/clustering | DEMO ONLY | Controlled tests | No reports in current DB | Isolated controlled demo only | NOT VERIFIED | Existing stack | Client-supplied demo identity; public POST; no abuse control or AI corroboration | Validate scoped acceptance |
| Citizen geographic map | PLACEHOLDER | Placeholder rendering test | NOT VERIFIED | Explain pending status only | NOT VERIFIED | Existing stack | No plotted geography/provider/submission form | Validate scoped acceptance |
| Authentication and three-role RBAC | IMPLEMENTED | Controlled tests | Three role accounts in DB; anonymous 401 observed | YES with existing accounts | NOT VERIFIED | Existing stack | No password reset/MFA/SSO/lockout; demo HTTP; Employee cannot manage accounts at all | Rehearse role journeys without changing production data in audit |
| User access administration | IMPLEMENTED | Controlled tests | NOT VERIFIED | YES, use designated test accounts | NOT VERIFIED | Existing stack | No billing/subscription product or self-service recovery | Validate scoped acceptance |
| Container deployment and host worker | IMPLEMENTED BUT PARTIAL | Controlled tests | Two healthy containers and current live artifacts | YES on this host | NOT VERIFIED | Existing stack | Not portable turnkey install; local absolute paths and ignored assets; no HTTPS termination | Validate scoped acceptance |
| Backups/recovery | IMPLEMENTED BUT PARTIAL | Controlled tests | Manual historical DB copies; scheduled recovery NOT VERIFIED | Do not promise operational backup protection | NOT VERIFIED | Existing stack | Backup service not running; backup volume absent; evidence/config not backed up | Validate scoped acceptance |
| Prediction / forecasting | NOT IMPLEMENTED | Unavailable UI only | NOT VERIFIED | DO NOT DEMO | NOT VERIFIED | Existing stack | No model, forecast API, training or forecast validation | Validate scoped acceptance |
| LPR/ANPR / real speed / cross-camera re-ID | NOT IMPLEMENTED | NOT AVAILABLE | NOT VERIFIED | DO NOT DEMO | NOT VERIFIED | Existing stack | Suitable data/calibration/models/validation absent | Validate scoped acceptance |
| External alerts and municipal dispatch | NOT IMPLEMENTED | NOT AVAILABLE | NOT VERIFIED | DO NOT claim automated response | NOT VERIFIED | Existing stack | No verified SMS/email/push/dispatch/integration pipeline | Validate scoped acceptance |

## 25. Master project status

| Domain | Current status | Evidence | Biggest gap |
| --- | --- | --- | --- |
| PRODUCT | Controlled-demo MVP/prototype; not production-ready | Recorded sources, live Camera3, review workflow | A validated municipal operational outcome |
| AI | Detection/tracking functional; event validity partial | 220 tests; limited real day evidence | Natural stopped-event positive and labeled accuracy |
| VIDEO | Five recorded scenarios + one selected live camera | ffprobe, current status/JPEG, healthy serving stack | Night quality and sustained reliability |
| BACKEND | Operational but suite has1 failure | 247 tests pass/1message mismatch; healthy API | Review/provenance semantics and acceptance tooling |
| DATABASE | Snapshot integrity OK;3event rows | Read-only quick_check/FKcheck;2329samples snapshot | Recovery including evidence, retention and source linkage |
| FRONTEND | Compiles;59 component tests; login visible | Current build asset names match served index | Recorded frame/review truth, authenticated browser acceptance |
| AUTH | Three-role implementation enforced | Runtime auth_required;401 reads; role tests | Production identity lifecycle and recovery |
| SECURITY | Demo hardening exists; not production perimeter | Cookies/hash/RBAC/headers; HTTP all-interface ports | TLS/network/rate controls and citizen abuse protection |
| INCIDENTS | Shared persistence/review exists; rule validity incomplete | 3DB rows + historical review artifacts | Correct natural incident and immutable provenance |
| ANALYTICS | Real sparse observation aggregation | 2329 Camera3 samples at snapshot | Throughput unavailable; temporal gaps/calibration limits |
| CITIZEN | Backend demo foundation, frontend map placeholder | 0stored reports; clustering code/tests; explicit placeholder | Trusted identities and actual geographic workflow |
| DEPLOYMENT | Working local hybrid stack | Backend/frontend healthy; host AI; backup absent | Portable secure recovery-tested pilot package |
| TESTING | Controlled coverage substantial but not all green | 220AI/59frontend pass;247backend pass/1fail | Fresh safe E2E and real-world acceptance |
| DEMO | Conditional, rehearsed recorded demo preferred | Usable H.264 assets; live day evidence | Avoid false stop/wrong-way/map/forecast/production claims |

## 26. Terminology, provenance and integrity

- **IMPLEMENTED:** code exists and works under stated controlled conditions.
- **TESTED:** a named automated/controlled check passed. The check's scope is part of the result.
- **REAL-WORLD VALIDATED:** demonstrated on appropriate real footage/conditions; Camera3 day detection is not night event validation.
- **DEMO-READY:** safe within a rehearsed controlled presentation, with stated labels/limits.
- **PRODUCTION-READY:** suitable for real municipal deployment including security, recovery, monitoring and correct workflow. Not established here.
- **NOT VERIFIED:** evidence missing, stale, contradictory or intentionally not exercised.
- **CALIBRATION READY:** geometry passed configured checks; not an algorithm acceptance result.
- **VERIFIED incident:** human-selected DB review status; not measured detector precision.
- **Frame observation:** repeated model view of an object at a moment; not unique traffic throughput.

The audit compared SHA256 for120 baseline source/config files before and after safe checks. Changed baseline files: **0**. Deployed backend Python hash differences: **0**. Served frontend JS/CSS asset names match the temporary current-source build. No source/config fix was applied. JSON preserves the preexisting dirty worktree and selected runtime metadata, so current local work is not mistaken for committed history. No Git commit/push occurred.

Current live/source files are mutable by their running producers; the embedded timestamped JSON snapshot is the report's time-bound evidence. Historical diagnostics were read as historical claims supported by retained images/state files, not blindly promoted to current validation. Not every dependency implementation, every old output frame or every current protected UI state was independently executed. Remaining verification limits are explicit in JSON. Secrets, password hashes and tokens are not included.

**Immediate single next action:** obtain and label one genuine daytime moved→inside stopped ROI→stationary for at least8s sequence, then use a separate scoped acceptance task to validate the complete stopped-event pipeline, while addressing the independently identified P0 truth/safety defects before claiming release readiness. Do not lower thresholds or relabel the existing parked-car false positive to manufacture success.

# CITYEYE IN ONE PAGE

**What is CityEye?** A local traffic-video analysis and human-review MVP using YOLO/ByteTrack plus calibrated temporal rules.

**Who is it for?** Intended for municipal traffic operators and administrators, with a limited citizen-facing foundation; no verified customer deployment.

**What goes in?** Selected DVR RTSP footage, local recorded MP4 scenarios and independent citizen report JSON.

**What happens inside?** Capture/decode, road-user detection/tracking, trajectory/ROI reasoning, proposed event/evidence generation, live import into SQLite, API delivery and operator review. Citizen clustering runs independently.

**What comes out?** Annotated live/recorded views, frame-based counts, traffic-state labels, proposed incidents/JPEG evidence, review/audit records and sampled historical analytics.

**Who benefits?** Intended beneficiaries are operators and road users; measured operational benefit is NOT VERIFIED.

**What works today?** Existing recorded assets including Maydan, limited daylight Camera3 detection/tracking, guarded live metrics, DB persistence, three-role access, evidence/review mechanics and real sampled analytics. AI220/frontend59 tests pass; backend247 pass and1 fails.

**What does not work or remain incomplete?** Genuine stopped positive acceptance, Camera3 Wrong Way/Blockage validation, functional Citizen Map/corroboration, prediction/LPR, operational scheduled backup, and several frontend truth/error paths. Current authenticated browser E2E was not rerun.

**Biggest technical gap?** A trustworthy natural incident chain, with ground-truth event correctness and UI confirmation matching the persisted result.

**Biggest product gap?** A validated municipal operator workflow/outcome beyond viewing and Verify/Dismiss, with agreed field acceptance criteria.

**Biggest deployment gap?** Reproducible, secure, recovery-tested operation beyond a hybrid local demo workstation.

**What should we build next?** Resolve the specific P0 review/timeline/disabled-calibration/test issues and validate a genuine moved-then-stopped sequence; then repair acceptance tooling, provenance and operational recovery.

**What should we NOT build yet?** Forecasting, LPR, larger fleets, more incident classes or a full citizen platform before the current evidence-to-decision workflow is reliable.

# WHAT CITYEYE ACTUALLY IS TODAY

CityEye is a functioning local traffic-monitoring MVP with real computer-vision processing and a municipal-style web interface. It can display five preprocessed recorded scenarios and a selected live DVR camera, produce road-user observations and retain proposed incident evidence for human review. Camera3 has limited daytime detection/tracking and road-ROI evidence, but a valid natural moved-then-stopped incident has not been demonstrated. Its wrong-way and road-blockage rules are intentionally disabled, and the historical VERIFIED wrong-way row is not proof that those rules are correct. Authentication and Admin/Employee/Citizen separation exist, while the Citizen Map itself is still a placeholder. Historical analytics contain real sampled observations, not unique vehicle throughput or predictions. Controlled tests establish many mechanics, but one backend test fails and the audit identifies concrete review, timeline and disabled-calibration safety defects. The system is suitable for a carefully labeled, rehearsed demo and further supervised engineering validation; the evidence does not support describing it as a production municipal platform.
