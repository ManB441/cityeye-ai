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

## T02 — Recorded timeline and truthful counters (P0)

Scope: AI per-frame output, backend timeline and recorded playback counters.
Reproduce missing zero-detection frames; emit an explicit zero observation where analysis actually ran, distinguish missing analysis from zero, and preserve correct seeking/source boundaries.
Acceptance: positive → zero → positive fixture matches frame timestamps; zero periods never inherit earlier vehicles; missing data remains unknown; seek/replay/source switching are correct.
Tests: AI output and backend timeline regressions plus frontend playback tests. Resolve the known backend timeline message assertion against the intended API contract without weakening numeric checks.
Depends on: baseline only. Deliver a separate commit with fixture-based evidence.

## T03 — Disabled-calibration safety (P0)

Scope: bicycle aggregation when a calibration-dependent congestion rule is absent; camera-specific safe fallback.
Reproduce the potential `int(None)` path before changing it. Avoid activating generic geometry for uncalibrated cameras.
Acceptance: bicycle detections with disabled calibration do not crash; unavailable traffic status stays UNKNOWN; camera identity/resolution and polygon validation still reject invalid profiles.
Tests: targeted AI regression including vehicles/persons/bicycles, disabled and valid profiles. No new ROI or thresholds.

## T04 — Incident queue consistency and review experience (P1)

Scope: stale polling responses, source switching during requests, review races, history refresh and detail usability.
Acceptance: a GET started before a completed review cannot revert the saved status; switching away and back does not accept an obsolete request; pending/error state is source-scoped; review status is consistent between card/detail/Incidents after reload; Escape/focus and evidence-image failure are usable.
Tests: deferred-response race tests, both review decisions, source switch, reload and keyboard interaction. Keep concurrency fixes separate from cosmetic changes if necessary.
Depends on T01.

## T05 — Stopped Vehicle end-to-end (P0 validation)

Scope: moving → inside valid ROI → stationary for configured duration → one proposed event → evidence → DB → review.
Observe Camera 3 over a documented reasonable interval. Record track, transitions, duration, UUID, evidence, DB status and review outcome. If no qualifying natural sequence occurs, mark REAL CAMERA NOT VALIDATED and use the existing recorded scenario for a separately labeled RECORDED DEMO test.
Acceptance: pre-existing parked vehicles produce no event; one episode produces one event; continued stationary frames do not repeat it; existing rearm behavior permits a subsequent eligible episode. Verify persistence/evidence using an isolated test database.
Tests: state-machine regression plus recorded pipeline and import/review integration. Only a demonstrated minimal algorithm bug permits a behavior change.
Depends on T01 and T03. A lack of real-world opportunity is not a passing result.

## T06 — Live preview and reconnection reliability (P1)

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
