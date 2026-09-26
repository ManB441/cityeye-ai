# T05 — Stopped Vehicle validation, 2026-09-24

**PARTIAL: real-camera positive validation is NOT VALIDATED; recorded positive acceptance FAILS. Controlled synthetic pipeline checks PASS. These are separate results.**

## Camera 3 real validation

Observed 300.9 seconds beginning 2026-09-24T17:32:52.709772+00:00; 151 samples, 151 distinct sampled AI frame numbers, 151 distinct preview hashes. Maximum observed vehicles/tracks: 0/0.

Moving observed: NO. Stopped transition: NO. ROI valid for current image: NO (configured daytime polygon is geometrically present; current dark/glared image does not support visual validation). New event/evidence/DB record: NO. No UUID or incident status exists for a new stopped episode. Production DB read-only query returned 0 STOPPED_VEHICLE records. Before/after event artifacts contain 0 new events.

No production per-track timer is exposed. With zero sampled tracks, there are no track IDs, ROI memberships or stationary durations to report; these are unavailable, not numerical zero-duration evidence. Snapshot/overlay are validation images, not event evidence. The overlay displays existing coordinates only and does not approve them for nighttime use. The existing 8-second threshold and manual nighttime-disable requirement remain unchanged.

## Recorded scenario validation — RECORDED DEMO

Reran the current model/configuration against all 318 frames (1920×1080, 30.0 FPS). 1672 detection/track rows, 93 distinct assigned IDs; zero events. Assigned IDs establish tracking execution, not robust long-term identity: substantial ID churn remains a limitation.

Event generated: NO. Evidence: NO. DB persistence of new recorded proposal: NO. Positive duplicate suppression: NOT VALIDATED. Clip threshold is 1.5 seconds, not Camera 3's 8 seconds. The prominent vehicle is already stopped with hood/trunk open in the first reference image. Zero events is not proof of a successful positive stop, and may be appropriate for pre-existing stationary vehicles. The generic scenario ROI has no declared reference resolution; no new spatial calibration claim is made.

## Synthetic regression — explicitly NOT Camera 3 or recorded-demo validation

Used current Camera 3 thresholds and calibrated geometry, with artificial trajectories and a clearly labeled synthetic image. Actual EventPipeline produced exactly two STOPPED_VEHICLE proposals: one per episode at 10.4s and 26.4s after motion/rearm, each with 8 seconds stationary. A separate vehicle stationary from the beginning produced none. Continued stationary observations produced no duplicate incidents.

Generated UUIDs: fc4d48a6-46e3-4c72-9ab6-ff861be26fba, 08c344e0-d5e8-4962-834e-39ff6ec5dd40. See `synthetic/events.json`, `synthetic/states.json`, and generated JPG evidence. These artifacts never entered the production database.

Four isolated backend cases (EMPLOYEE/ADMIN × Verify/Dismiss) automatically imported the generated events, served exact evidence bytes, exposed incident list/detail endpoints, preserved decisions through replay and backend restart, and retained exactly two records. Temporary databases were removed. UI tests separately verified stopped details, View, Verify/Dismiss and remount persistence using controlled API responses; this was not a manual browser-to-production-DB exercise.

## Checks and changes

38 stopped/pipeline AI tests, 11 backend importer tests, and all 77 frontend tests passed; TypeScript passed. No production behavior changed. Two stopped-review frontend regressions were added. Diagnostic scripts ran outside the worker; no production instrumentation was installed. The existing historical September 18 report remains untouched in the parent directory.

## Acceptance status

STOPPED VEHICLE:
REAL CAMERA = NOT VALIDATED
RECORDED SCENARIO = FAIL

PIPELINE:
Detection = PASS (recorded detections only)
Tracking = PASS (recorded assigned IDs; continuity not certified)
State transition = FAIL (no observed qualifying natural transition; synthetic regression passes)
Event = FAIL (no qualifying real/recorded positive event; synthetic generation passes)
Evidence = PASS (synthetic pipeline only)
DB persistence = PASS (isolated synthetic import only)
Review workflow = PASS (isolated API and frontend regression only)
Duplicate suppression = PASS (synthetic episode/rearm and import replay only)

## Single next action

Capture a clear daytime Camera 3 sequence showing sustained movement inside the existing ROI, followed by at least 8 seconds stopped, then rerun positive acceptance. Do not mark the feature end-to-end validated before that evidence exists.
