# P0 #2 — Live truth and metric semantics

Implemented on 2026-09-17. No commit or push. P0 #1 incident persistence, authentication, detector/tracker settings and event algorithms are unchanged by this task.

## 1. Root causes and traced paths

Camera 3 writes `live_metrics.json` and `camera_status.json` into its configured output directory. Previously the backend returned unqualified metric values (including default zero values for a missing file); the UI checked generation but not age or source identity. Analytics accepted any positive timestamp with ONLINE/matching generation.

The dashboard used `liveMode && currentLiveMetrics ? liveMetrics : currentFrame`, so absent live metrics selected the recorded timeline. Traffic status treated a proposed event as Attention, otherwise Normal except for heavy congestion, losing MODERATE. AI imagery depended on camera health alone. Camera health, metrics and incidents were fetched together, coupling independent failures. Recorded hooks retained the previous scenario's results while another scenario loaded. Late requests could replace current source state.

Recorded flow remains selected scenario → analysis timeline → latest frame at/before video position. Live flow is now selected camera directory → validated server snapshot → bounded client snapshot → current observation. Sidebar selection and recorded request ownership explicitly match the selected source.

## 2. Files changed for this task

Backend:
- `backend/app/live_camera.py`: centralized snapshot validation and continuous AI stream freshness checks.
- `backend/app/schemas.py`: snapshot envelope and health validity metadata.
- `backend/app/main.py`: metrics envelope and AI stream gates.
- `backend/app/operational_analytics.py`: reuse the same snapshot guard.
- `compose.yaml`: forward the AI maximum-age setting.

Frontend:
- `frontend/src/types.ts`, `frontend/src/api/live.ts`: snapshot contract and conservative monotonic deadlines.
- `frontend/src/lib/liveTruth.ts`: shared freshness and traffic-label logic.
- `frontend/src/pages/MunicipalDashboard.tsx`: explicit source mode, null semantics, independent incident state, generation and source guards.
- `frontend/src/pages/CamerasPage.tsx`, `frontend/src/components/SourceSidebar.tsx`: matching validity and correct capture FPS label.
- `frontend/src/hooks/useAnalysis.ts`, `frontend/src/hooks/useEvents.ts`: source ownership and late-response protection.

Tests/documentation:
- `backend/tests/test_live_truth.py` (new).
- `backend/tests/test_live_camera.py`, `backend/tests/test_operational_analytics.py` (adapt existing fixtures/assertions to the contract).
- `frontend/src/pages/MunicipalDashboard.test.tsx` (new).
- `LIVE_TRUTH.md` (this document).

Other dirty files predate this task; they are not newly claimed as P0 #2 changes.

## 3. Source model

`LIVE_CAMERA(id)` and `RECORDED_SCENARIO(id)` are an explicit union. Live counts never use a recorded frame. Recorded counts never use live metrics. Missing data is null; a valid zero is retained. Source switches clear source-dependent displayed state, and asynchronous responses cannot populate another selected source.

## 4. Freshness contract

Both live metrics endpoints now return an envelope (an intentional API response change):

- `camera_id`, `checked_at`, `max_age_seconds`, `valid_for_seconds`.
- `reason`: FRESH, MISSING, INVALID, STALE, OFFLINE, SOURCE_MISMATCH or GENERATION_MISMATCH.
- `health`: sanitized status with server validity budget.
- `metrics`: complete observation when FRESH, otherwise null.

The server requires configured camera identity to match health, ONLINE with a current heartbeat, matching generation, and a finite positive AI timestamp no later than backend time and no earlier than the connection start. Metric age must be strictly below `CITYEYE_LIVE_AI_MAX_AGE_SECONDS` (default 5 seconds; configurable above 0 and at most 10). This is conservative relative to the current several-AI-frames-per-second worker and 2-second UI polling. Heartbeat validity retains the existing default 10-second threshold. Missing/incomplete snapshots never become synthetic zero counts.

The existing worker's metrics file has no camera ID: identity is bound to its configured directory and verified against health. If a metrics camera ID is present it must match too. AI output format is unchanged.

The client subtracts the entire HTTP round trip from the server's remaining budget, using `performance.now()` rather than browser wall time. A 250 ms render timer, focus/visibility refresh, and current-health/generation/connection checks invalidate cached metrics even when polling fails. Polling is serialized, aborted on unmount/source change, and bounded to 4 seconds per cycle.

## 5. Stale, generation and offline behavior

Fresh raw preview remains available when AI data is missing/stale. AI counts, frame number and AI FPS become —, traffic condition becomes Unknown, and the UI shows WAITING FOR AI. AI view stops showing the stale processed image. The backend refuses a stale AI stream and closes an existing AI stream after its guard detects stale data.

An observed generation or connection-start change immediately invalidates the previous observation; no values reappear until a compatible fresh snapshot arrives. OFFLINE/RECONNECTING removes live counts and images. Persistent incidents are not deleted or reset. Health itself also expires locally if server requests stop.

## 6. Traffic and incident semantics

NORMAL → Normal; MODERATE → Moderate; HEAVY_CONGESTION → Heavy congestion; CONGESTED → Congested; unsupported/missing → Unknown. No detector threshold is changed. The recorded CSV contains counts but no per-frame condition, so its condition is Unknown rather than inferred from a scenario title or historical incident.

Pending/reviewed incidents are independent persistent records. A ten-minute-old WRONG_WAY proposal remains an incident without changing current density/condition. Incident request failure cannot supply or fabricate metric values.

## 7. Metric meanings (verified against the existing producer)

- Vehicles: current-frame motorized detections, cars + buses + trucks + motorcycles; includes valid untracked detections.
- Cars, Buses, Trucks, Motorcycles: current-frame detections of the named class.
- Bicycles and People: current-frame bicycle/person detections, separate from Vehicles.
- Tracks: distinct tracker IDs emitted in the current AI frame, including supported non-motorized road users; not cumulative IDs.
- Moving / Stationary: currently tracked motorized vehicles assigned that movement state. Unknown movement is a separate category; these are not necessarily equal to the total detection count.
- Capture FPS: raw capture callbacks per second over the existing rolling approximately 5-second window.
- AI FPS: completed AI processing cycles per second over the existing rolling 5-second window, including processing work; not raw capture rate or pure model benchmark FPS.
- Preview FPS: published raw-preview frames per second over the existing rolling window; independent of AI FPS.

These are current observations/window rates, never daily totals, unique crossings or throughput. No new throughput calculation was added.

## 8. Analytics protection

The collector uses the same `read_live_snapshot` contract. Stale, missing, wrong-camera, wrong-generation or offline observations are skipped even when a heartbeat is still present. Existing aggregation, storage intervals, deduplication and historical records remain unchanged. This does not retroactively repair previously stored observations.

## 9. Acceptance and regression

Real Chrome used the actual updated frontend and backend with temporary credentials, database, controlled camera output and existing recorded video. No real Camera 3 status/metrics were altered.

Observed sequence: recorded Congestion at 6 seconds = 30 vehicles → switch to missing live = — → fresh live = 7/Moderate → stale AI = —/Unknown with raw JPEG still decoded → AI view unavailable → fresh zero = 0/Normal → mismatched generation hidden → new generation = 8 → reconnecting hidden → restored live = 7 → recorded = 30 again. The two controlled persisted incidents remained visible and accessible in Incidents. No browser page errors. The old PROPOSED incident case is additionally covered by the component regression.

The rebuilt normal local app was also checked in Chrome: anonymous events request returned 401, the existing admin account signed in, Camera 3 returned FRESH (generation 5, zero current detections), the raw preview decoded, and the original single incident remained PROPOSED. No page errors. Read-only backend inspection measured approximately 0.14 seconds metric age and 4.0 AI FPS. Temporary acceptance servers were stopped afterwards.

Screenshots: `/tmp/cityeye-p0-browser/truth-recorded.png`, `truth-fresh.png`, `truth-stale.png`. The gray test JPEG is intentional synthetic evidence, not the real camera image.

Regression: backend 242, AI 188, frontend 55 = 485 passing tests (baseline 455, +30). Backend suite includes authentication/RBAC/audit, persistent live ingestion/review, and analytics. Frontend production build and Docker build pass. `git diff --check` passes. The local backend/frontend were rebuilt; the Camera 3 AI worker was not restarted or reconfigured.

## 10. Limits

Five seconds measures the published observation's wall-clock age, not end-to-end sensor/DVR latency or model accuracy. AI/backend host clocks must be synchronized. Generation detection is polling-based (normally within the 2-second poll cadence), not instantaneous push; once observed, the old generation is invalid immediately. Browser background timer throttling is mitigated by expiry checks on focus/visibility and server-side stream checks. Identity relies on the existing configured output-directory binding because the worker does not publish an explicit metrics camera ID. Recorded condition remains Unknown until a genuine per-frame source exists. No new multicamera capability, accuracy claim, incident verification or historical analytics repair is included.
