# CityEye: existing-feature stabilization plan

Created 2026-09-24. Work proceeds sequentially, with a bounded change, regression tests and an independently reviewable commit for each task. No new feature development in this cycle. Findings originate in the current-state audit; this plan does not certify unobserved camera behavior.

## Working agreement

- Preserve YOLO, ByteTrack, thresholds, camera geometry and unrelated event logic unless the specific task supplies evidence of a bug and explicitly documents the necessary change.
- Reproduce each bug first; define acceptance before implementation. Test failure paths as well as success.
- Use isolated databases and fixtures. Do not run mutating smoke tests against the operational database.
- Distinguish automated regression, recorded-demo validation and observed real-camera validation.
- No task is complete just because code ran. Record commands, results, remaining limitations and evidence.
- Keep secrets, databases, model weights, camera imagery and video assets out of Git. Local audit and diagnostic artifacts remain local.
- Save the pre-existing source/configuration baseline separately; publish the first fix on `codex/feature-stabilization`. Subsequent tasks remain queued for separate execution.

## T01 — Truthful incident review (P0, implemented)

Scope: Command Center Verify/Dismiss for recorded and live incidents.
Problem: recorded review swallows an API failure and the dialog fabricates a successful status; live review rejection has no visible error handling.
Change: propagate the saved event to the dialog, catch failures in the dashboard, keep a separate review error through polling, allow retry, and ignore results after a source selection changes.
Acceptance: HTTP failure leaves PROPOSED; Verify and Dismiss each display errors in both modes; polling does not erase the failure; successful retry uses the server response; existing frontend checks pass.
Tests: four regression cases cover the live/recorded × verify/dismiss matrix. These mock API behavior and do not certify database persistence or real-camera events.
Out of scope: redesigning dialogs, event algorithms, and comprehensive concurrent-review/poll ordering (T04).

## T02 — Recorded timeline and truthful counters (P0, implemented)

Scope: AI per-frame output, backend timeline and recorded playback counters.
Reproduce missing zero-detection frames; emit an explicit zero observation where analysis actually ran, distinguish missing analysis from zero, and preserve correct seeking/source boundaries.
Acceptance: positive → zero → positive fixture matches frame timestamps; zero periods never inherit earlier vehicles; missing data remains unknown; seek/replay/source switching are correct.
Tests: AI output and backend timeline regressions plus frontend playback tests. Resolve the known backend timeline message assertion against the intended API contract without weakening numeric checks.
Depends on: baseline only. Deliver a separate commit with fixture-based evidence.

## T03 — Disabled-calibration safety (P0, implemented)

Scope: bicycle aggregation when a calibration-dependent congestion rule is absent; camera-specific safe fallback.
Reproduce the potential `int(None)` path before changing it. Avoid activating generic geometry for uncalibrated cameras.
Acceptance: bicycle detections with disabled calibration do not crash; unavailable traffic status stays UNKNOWN; camera identity/resolution and polygon validation still reject invalid profiles.
Tests: targeted AI regression including vehicles/persons/bicycles, disabled and valid profiles. No new ROI or thresholds.

## T04 — Incident queue consistency and review experience (P1, implemented)

Scope: stale polling responses, source switching during requests, review races, history refresh and detail usability.
Acceptance: a GET started before a completed review cannot revert the saved status; switching away and back does not accept an obsolete request; pending/error state is source-scoped; review status is consistent between card/detail/Incidents after reload; Escape/focus and evidence-image failure are usable.
Tests: deferred-response race tests, both review decisions, source switch, reload and keyboard interaction. Keep concurrency fixes separate from cosmetic changes if necessary.
Depends on T01.

## T05 — Stopped Vehicle end-to-end (P0 validation, DEFERRED by user — natural positive evidence pending)

Scope: moving → inside valid ROI → stationary for configured duration → one proposed event → evidence → DB → review.
Observe Camera 3 over a documented reasonable interval. Record track, transitions, duration, UUID, evidence, DB status and review outcome. If no qualifying natural sequence occurs, mark REAL CAMERA NOT VALIDATED and use the existing recorded scenario for a separately labeled RECORDED DEMO test.
Acceptance: pre-existing parked vehicles produce no event; one episode produces one event; continued stationary frames do not repeat it; existing rearm behavior permits a subsequent eligible episode. Verify persistence/evidence using an isolated test database.
Tests: state-machine regression plus recorded pipeline and import/review integration. Only a demonstrated minimal algorithm bug permits a behavior change.
Depends on T01 and T03. A lack of real-world opportunity is not a passing result.

## T06 — Live preview and reconnection reliability (P1, implemented; natural recovery timing not observed)

Scope: stream failure, stale health, recovery and generation transitions.
Acceptance: stale/offline feeds do not appear live; raw and AI views recover after reconnect; old-generation metrics remain unknown; a timed soak records reconnects per observation duration, dropped frames and recovery latency.
Tests: stream/health failures, retry recovery and generation mismatches; controlled observation with a documented duration. No threshold tuning to hide failures.
Document existing Camera 3 daylight-only operation and manual night shutdown; do not silently override the user's decision to keep daytime calibration enabled.

## T07 — Maydan Palestine recorded source (P1)

Scope: inspect actual frames, confirm source metadata and calibrate only visible, defensible traffic regions using the existing configuration mechanism.
Acceptance: playback and analysis refer to the same source/time; bounding boxes and ROI align at the actual resolution; no invented geographic coordinates or direction; unsupported rules remain disabled; recorded outputs are labeled RECORDED DEMO.
Tests: frame/coordinate checks, representative overlays and pipeline regression. Natural event absence is reported honestly. Video stays local.
Depends on T02 and T03.

## T08 — Role access and citizen report integrity (P1)

Scope: preserve ADMIN full access; EMPLOYEE operational access without account administration; CITIZEN limited to permitted citizen/map functions. Eliminate trust in client-supplied voter identities for report consensus.
Acceptance: direct protected API requests are rejected for unauthorized roles, not merely hidden in the UI; spoofing repeated client identities cannot manufacture confirmation; existing login/session behavior remains intact.
Tests: isolated role matrix, forged requests, duplicate reports, expired session and logout. Existing citizen map is a placeholder; implementing a new map is outside this stabilization cycle.

## T09 — Operational analytics correctness (P1)

Scope: source identity, sample-based counts, real timestamps and congestion labels.
Acceptance: sampled detections are not labeled unique throughput; missing minutes remain gaps; cameras cannot merge through a shared display name; moderate and heavy conditions are distinguished; empty/stale/error states are explicit.
Tests: multi-camera fixtures, irregular sample timing, zero/missing periods and UI rendering. Do not invent unavailable speed or forecast data.
Depends on T02.

## T10 — Repeatable tests, backups and reproducibility (P1)

Scope: isolate the obsolete smoke script, align role names, document runtime prerequisites and verify backup restoration safely.
Acceptance: smoke tests leave the operational DB unchanged; a backup restores into a disposable database with integrity checks; required config/model/video prerequisites and versions are documented; absent local assets produce actionable errors.
Tests: temporary DB smoke run, backup/restore rehearsal and clean-checkout build. Never restore over the live DB.
Define deployment hardening (TLS, exposure, rate limits) separately before public deployment; do not expose services as part of testing.

## T11 — History scale and final regression (P1/P2)

Scope: bounded history queries/pagination, storage retention policy and stale documentation.
Acceptance: large synthetic histories remain bounded; page boundaries have no duplicates/missing records; retention policy preserves referenced evidence and requires explicit destructive-action authorization; docs reflect actual features and limitations.
Tests: scale fixtures, pagination and reference integrity. Finish with AI/backend/frontend suites and a documented operator walkthrough across live, recorded, incidents, review and role access.
Depends on earlier tasks. Final report lists each feature as validated, partial or blocked with evidence, rather than asserting everything works.

## First-fix validation record

Before T01, added regressions reproduced false VERIFIED state in recorded review and an unhandled HTTP 500 rejection in live review. After the change, the four review cases must pass alongside the existing frontend suite, TypeScript checking and production frontend build. This change does not claim to resolve the unrelated backend timeline assertion or unobserved natural stopped-vehicle validation.

Completed T01 checks (2026-09-24):
- `cd frontend && npm test -- --cache=false`: 63 tests passed across 5 files, including all four new review regressions.
- TypeScript app and node configuration checks: passed (temporary node build-info output).
- Vite production build: passed, 62 modules; output written to `/tmp/cityeye-stabilization-build`, not deployed over the running application.
- `git diff --check`: passed.
- Production database and camera/event processing were not changed by T01. Earlier baseline work is intentionally in its own commit.


## T02 validation record — 2026-09-24

The existing AI producer already writes every processed recorded frame to `traffic_timeline.json`; no YOLO, ByteTrack, thresholds or producer changes were needed. The backend now combines valid processed-frame observations with detection rows. An observed frame without detections has zero counts; arbitrary gaps in CSV are not filled. Summary counts also use the last observed frame, including a trailing empty frame.

Recorded observations expose `duration_sec`, inferred from the median timestamp/frame interval of the existing fixed-rate output. The frontend stops retaining counts beyond that observation interval and shows unknown during gaps. A single observation cannot establish a duration; its duration is null and is not held into later playback. Legacy frontend fixtures without this new field retain compatibility. This duration calculation assumes the current fixed-rate recorded pipeline, not a variable-rate external timeline.

Evidence and checks:
- Regression failed before the change: observed empty frames 1 and 4 were absent; only detection frames 0 and 3 were returned.
- Actual local `rainy_traffic` artifacts, read without modification: 611 CSV frame groups became 787 observations, including 176 zero-vehicle frames.
- Backend: 251 tests passed. Includes empty observations, missing-frame gaps, invalid manifest rejection, trailing-zero summary and existing API tests.
- Frontend: 64 tests passed. Includes positive → zero → missing/unknown → positive, backward seek and playback beyond the final observation; existing source-switch tests also passed.
- TypeScript app/node checks and production Vite build passed; build output is in `/tmp/cityeye-t02-build`.
- Updated the pre-existing timeline test's outdated message expectation while retaining exact count assertions.

Limitations: this is validation against saved AI outputs and automated playback fixtures, not a new model inference or live-camera event validation. The changes are not deployed to the running application. Manifest and CSV must belong to the same completed analysis run; artifact generation identity/atomic multi-file publication remains a separate provenance concern.


## T03 validation record — 2026-09-24

Two minimal fixes:
- Bicycle diagnostic ROI counting now handles unknown membership without `int(None)`. The underlying `bicycle_in_road` remains None when there is no calibrated rule; it is not relabeled as a confirmed outside-road detection.
- An RTSP configuration with a camera calibration registry now requires a matching camera profile. Missing profiles disable geometry-dependent rules with an explicit diagnostic instead of falling back to generic geometry. Recorded configurations and legacy configurations without a registry preserve their existing behavior.

Regression evidence: adding a bicycle to the existing simulated worker reconnect/resolution test reproduced a crash on the mismatched-resolution frame. Missing-profile tests also failed before the fix. Afterward, the worker processes car/person/bicycle detections through valid → invalid resolution → restored calibration, retains UNKNOWN traffic during invalid calibration, resets tracks on reconnect and emits no spurious event. Camera-5/camera-7 profile tests verify generic geometry is not activated, even when a generic direction is supplied.

Validation: all 222 AI tests passed using a temporary test directory (`PYTHONDONTWRITEBYTECODE=1 ai/.venv/bin/python -m pytest ai/tests -q -p no:cacheprovider --basetemp=/tmp/cityeye-t03-ai`). This includes existing bounds, degenerate/self-intersecting polygons, zero direction, identity and resolution validation. `git diff --check` passed.

No production camera configuration, model, tracking algorithm, threshold or ROI coordinates were changed. This is automated worker/pipeline regression with controlled detections, not a new real-camera observation. The running worker has not been restarted or deployed.


## T04 validation record — 2026-09-24

Reproduced the live polling race before fixing it: for both Verify and Dismiss, a delayed incident GET reverted the card to PROPOSED after a successful save, while the detail retained the saved status.

Changes:
- Version incident requests around reviews so responses begun before a completed save cannot overwrite it. Live metrics updates remain independent of this incident-only guard.
- Scope recorded requests and pending review state to a particular source selection, including A → B → A. A previous operation cannot clear a new pending operation or update the new selection.
- Serialize review actions within the active selection/page and disable review controls while saving.
- Synchronize open details with accepted incident refreshes. Recorded incident history now refreshes every two seconds alongside live history; unavailable recorded sources retain known incidents and display an error.
- Keep review errors separate from background loading errors.
- Show the saved review state in the detail banner, trap keyboard Tab navigation, close with Escape, restore opener focus and display a fallback when evidence cannot load.

Validation:
- 75 frontend tests passed across seven files, including 11 new regression cases.
- New cases cover live late-GET Verify/Dismiss, recorded late-GET reviews, A → B → A review isolation, old live success/failure isolation, externally reviewed recorded detail refresh, evidence failure, Escape/Tab/focus restoration and saved banners.
- Existing persistence-through-remount tests and failed-save retry tests continue to pass.
- App and node TypeScript checks passed; production Vite build passed (62 modules, temporary output `/tmp/cityeye-t04-build`). `git diff --check` passed.

These are frontend integration tests with controlled API responses, not proof of new database writes or live-camera events. Backend/AI algorithms and production data were not modified. The running application has not been redeployed. Requests initiated after a completed review remain authoritative, allowing legitimate later server updates rather than permanently pinning a local decision.


## T05 validation record — 2026-09-24

Status: PARTIAL. Real Camera 3 remains NOT VALIDATED; the current recorded clip does not pass positive moved-then-stopped acceptance. No production bug was demonstrated in this run and no production behavior was changed.

- Passive Camera 3 observation: 300.86 seconds, 151 samples, 151 distinct preview hashes and sampled AI frames. Maximum vehicles/tracks: 0/0. Current frames are dark/glared; the existing daytime ROI cannot be visually validated. No new live incident was generated. A read-only production DB query returned no STOPPED_VEHICLE rows.
- Actual recorded rerun: all 318 frames at 1920×1080/30 FPS, 1672 detection/track rows, zero events. The prominent car is already stopped at the beginning. Assigned track IDs do not establish physical movement or stable identity. The generic scenario geometry is not newly certified for this source resolution. No positive recorded event, evidence or DB persistence is claimed.
- Separate SYNTHETIC regression with existing Camera 3 geometry and 8-second threshold: two stopped episodes produce exactly two proposals after sustained motion/rearm. A pre-existing stationary track produces no event; continued stationary frames produce no repeats. Detection and ByteTrack are bypassed in this synthetic check.
- The actual generated synthetic proposals and evidence were automatically imported into temporary backend databases. Four cases (EMPLOYEE/ADMIN × Verify/Dismiss) verified evidence access, list/detail access, persisted review across restart and duplicate-import suppression. No synthetic proposal entered production.
- Added two stopped-vehicle review UI tests for View, measured details, Verify/Dismiss and remount persistence with controlled API responses. This is not a manual production browser validation.
- Checks: 38 stopped/pipeline AI tests, 11 backend import tests and all 77 frontend tests passed. TypeScript passed. Only tests and this plan changed in Git.

Local evidence is retained under `diagnostics/camera3-stopped-validation/2026-09-24/`: validation-report.json, validation-report.md, validation-frame.jpg, validation-overlay.jpg, raw observation samples, recorded outputs, synthetic outputs and diagnostic scripts. Historical reports remain untouched. Images, videos, local artifacts and temporary test credentials are excluded from commits.

Next action: obtain a clear daytime Camera 3 sequence with sustained movement inside the existing ROI followed by at least 8 seconds stopped, then repeat positive end-to-end acceptance. Do not label T05 complete until observed evidence supports it.


## T06 validation record — 2026-09-24

Fixed two reproduced issues: cumulative retry exhaustion after successful recovery, and raw MJPEG health checked only on connection opening. Raw/AI frontend retries now use a consecutive-failure budget independent of the URL token. Success, manual retry and source/mode changes restore the budget; backoff limits remain unchanged. Raw streams now close when existing health validity, source identity or connection generation checks fail, using the existing 250 ms currentness polling. AI freshness behavior is unchanged.

Validation: 252 backend tests, 80 frontend tests and 25 frame-source tests passed; TypeScript and production frontend build passed. Before fixes, all three new frontend retry regressions and the new raw endpoint currentness regression failed.

Passive Camera 3 observation: 120.24 seconds / 61 samples, all ONLINE, generation 127 throughout, reconnect counter 884 → 884, reported dropped-frame delta 0. Mean capture/preview/AI FPS: 12.03/10.95/3.95. No natural reconnect occurred; actual recovery latency remains unmeasured. No deliberate interruption of the sole camera, worker restart, production DB write or deployment was performed. This short sample does not certify long-term reliability.

Local report and telemetry: `diagnostics/live-reliability/2026-09-24/report.md`, `report.json`, `observation.json`, and test logs. Existing Camera 3 daylight-only calibration/manual nighttime-disable policy remains documented and unchanged. T05 is deferred at the user's request; a second camera is not required for these controlled reliability tests.
