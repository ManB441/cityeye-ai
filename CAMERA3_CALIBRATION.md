# Camera 3 calibration — blocked on a usable current road view

P0 #3 spatial safety and diagnostics are implemented. **Real road calibration is NOT complete.** The fresh Camera 3 image is severely obscured/defocused; no reliable road edges, lanes, vehicles or legal direction can be identified. No road geometry or traffic rule was invented. Camera 3's affected spatial rules now fail closed with CALIBRATION_REQUIRED, while preview, detection, tracking and persistent incidents continue.

No commit or push. No model, confidence, ByteTrack, event threshold/algorithm, auth, RBAC, frontend, analytics architecture, incident persistence or freshness-contract change was made for this task.

## 1. Actual frame

Decoded directly from the existing local raw preview publisher: **944 × 1080 pixels**, aspect ratio **0.874074:1**, portrait. Actual image bounds are x=0..943 and y=0..1079. No rotation/resizing was applied for calibration. At initial capture, raw preview age was about 0.03 seconds and camera heartbeat age about 0.20 seconds. The image is current, not an old screenshot; embedded DVR time is not used as the freshness clock.

## 2. Geometry inventory before changes

- Monitored road: `[(100,100),(1180,100),(1180,650),(100,650)]`. INVALID: two vertices outside the actual frame. Used by Congestion and as the inherited road geometry; its bounding diagonal supplied movement normalization.
- Stopped ROI: `[(100,360),(1180,360),(1180,650),(100,650)]`. INVALID: two vertices out of frame. Used by Stopped Vehicle.
- Wrong-Way near_lanes polygon: same as Stopped ROI. INVALID bounds. Arrow `(200,500) → (1080,500)`; vector `(880,0)`. Endpoint outside frame and no verified camera-specific legal-direction evidence.
- Wrong-Way far_lanes polygon: `[(100,100),(1180,100),(1180,359),(100,359)]`. INVALID bounds. Arrow `(1080,230) → (200,230)`; vector `(-880,0)`. Start outside frame and no verified camera-specific legal-direction evidence.
- Congestion: no dedicated ROI; uses monitored road polygon. Therefore INVALID for this image.
- Person/bicycle-in-road: no dedicated ROI; bottom-center diagnostic membership uses congestion/road polygon. Therefore INVALID. This is a membership annotation, not a newly enabled event.
- Road Blockage: no `blockage_zones`; CONFIGURATION REQUIRED and disabled.
- Masks: none configured/consumed for Camera 3.
- Lane polygons: only the two generic named direction zones above; no surveyed lane geometry.
- Normalized coordinates: none.

The saved before-overlay shows the image boundary and deliberately retains out-of-frame coordinates in a surrounding diagnostic margin. It does not clip them into apparently valid geometry.

## 3. Out-of-frame points

All `x=1180` polygon vertices exceed the last image column by **237 pixels**. Arrow coordinate `x=1080` exceeds it by **137 pixels**. The listed y coordinates are within frame, but that does not make their scene placement meaningful.

## 4. Root cause

The supervised worker loads shared `live_camera.json`, then overrides only camera ID/name for Camera 3. It inherited absolute pixel geometry from a generic Municipal Pilot template with horizontal near/far lane assumptions, without a camera-bound reference resolution or runtime spatial validation. A larger landscape image is suggested by those coordinates, but its exact original resolution/provenance is not recoverable from this configuration. Scaling or clipping that template cannot establish the real road in today's obscured portrait image.

## 5–8. Final geometry and direction

- Monitored road: **unavailable / no active polygon**.
- Stopped ROI: **unavailable / no active polygon**.
- Congestion ROI: **unavailable**, will share the confirmed monitored-road polygon when one can be justified.
- Allowed direction: **CALIBRATION REQUIRED / no active arrow or direction zone**.

The original generic values remain available for forensic comparison and legacy configuration compatibility, but the explicit Camera 3 profile overrides them; they cannot silently become Camera 3 fallback geometry. Road, Congestion, Stopped, Wrong-Way and person-in-road membership are unavailable for this profile. No pending historical incident was deleted, verified or dismissed.

## 9. Representation

Kept **absolute pixels with an exact camera ID and reference resolution**, rather than introducing normalized geometry. A resolution change disables affected spatial rules until explicit recalibration. Normalizing an unverified generic polygon would preserve the wrong scene assumptions. No broad geometry migration was needed and VIDEO_FILE configurations bypass the Camera 3 profile entirely.

## 10. Defensive validation / runtime behavior

New opt-in `ai/calibration.py` checks finite numeric points, strict frame bounds, at least three unique vertices, positive polygon area, degenerate edges, self-intersection, whole-edge containment inside the confirmed road (including concave boundaries), nonzero in-zone direction vectors, explicit visual/direction confirmation, camera identity and exact dimensions. Missing/malformed calibration fails closed with a clear per-rule diagnostic.

Invalid Stopped geometry disables Stopped alone when the road/direction are valid. Invalid direction disables Wrong-Way alone. Invalid monitored road disables dependent spatial rules. No dummy road or guessed direction is substituted. Road Blockage remains disabled for this calibration profile.

Validation runs before using the first actual frame, on dimension changes, and on generation changes. Tracker/trajectory state resets on resolution/generation transitions; persisted events are retained. Counts still describe current detections, while traffic condition is UNKNOWN when its spatial context is unavailable. Without a calibrated road scale, tracked vehicle movement is reported in the existing unknown-movement category rather than asserting road-normalized Moving/Stationary classifications. No timing/speed threshold values were tuned.

`ai/live_output/camera-3/calibration_status.json` is a local diagnostic report, written on validation transitions. Its `checked_at` is the validation time, not an AI freshness heartbeat. The annotated feed says `Traffic: UNKNOWN | CALIBRATION REQUIRED`. Existing backend/frontend freshness validation and response contracts are unchanged.

## 11. Road Blockage

**CONFIGURATION REQUIRED**. The implementation has overlap/obstruction and upstream traffic-impact concepts, but Camera 3 has no approved blockage polygon, usable lane/flow direction, or camera-specific evidence validating its upstream-impact assumptions. A road ROI alone would not establish these. No blockage zone, event type or algorithm was added/enabled.

## 12–13. Real observation and unexpected triggers

After one graceful restart of only the existing Camera 3 worker, a **120.28-second window with 60 samples** showed:

- ONLINE throughout; generation 1; no read errors.
- Capture FPS 11.82–12.47; AI processing FPS 2.0–4.2.
- Maximum observed AI metric age 1.75 seconds, below the unchanged 5-second freshness threshold.
- Zero vehicle detections and zero tracks in this obscured view. This is model output, not evidence that the real road was empty.
- Traffic condition UNKNOWN throughout.
- No new events; all pre-existing event IDs preserved.

Vehicle Detection, Tracking, Moving State, Stationary Transition: **NOT OBSERVED**. Wrong-Way, Stopped Vehicle and Congestion: **NOT VALIDATED**. No events is expected with spatial rules disabled and is not proof of calibrated event accuracy. The old single PROPOSED incident remains historical/unreviewed and is not evidence validating today's geometry.

Outside-road membership, partial edge vehicles, parked-to-moving transitions, near-edge directions and pedestrian/vehicle separation could not be assessed in real imagery because no usable road/vehicles appeared. Controlled tests cover the safety guard and the pre-existing algorithms; that is separate from real-world validation.

## 14. Recorded regression

Normal Traffic, Heavy Congestion, Stopped Vehicle and Rainy Traffic each processed 12 actual source frames using the unchanged model/configuration into separate `/tmp/cityeye-calibration-recorded/` outputs. All output videos decoded with 12 frames; config hashes remained identical. Detection-row counts were 148, 395, 70 and 0 respectively. Rain's first 12 frames legitimately produced no detections; an initial smoke assertion incorrectly required detections in every clip, so validation was corrected to require processing/decodable output rather than fabricate a nonzero count. No production scenario output was replaced.

Real Chrome also played all four existing recorded demos at 6 seconds and displayed their respective vehicle counts: Normal 15, Congestion 30, Stopped 4, Rainy 4. No page errors. No separate Wrong-Way recorded scenario is configured; its algorithm regression tests pass, but no clip acceptance is claimed.

## 15. Tests/build and preserved P0 behavior

- Backend **242 passed** (includes Auth/RBAC, incident persistence/review/audit, and live freshness/analytics).
- AI **218 passed** (188 baseline + 30 calibration tests).
- Frontend **55 passed**.
- Total **515 passed**; production frontend build PASS; `git diff --check` PASS.
- Live browser check after the worker restart: anonymous protected request 401, existing admin login succeeded, Camera 3 snapshot FRESH with 0 detections/UNKNOWN traffic, raw preview decoded, original single DB incident remained PROPOSED.
- No backend/frontend deployment was needed; only the AI worker was restarted. Its detector/tracker configuration and thresholds are unchanged.

## 16. Artifacts and reproducible diagnostic command

Final active-geometry diagnostic (accurately shows that no spatial geometry is currently approved):

`/Users/abcd/cityeye-ai/diagnostics/camera3-calibration/final-overlay.jpg`

Before comparison:

`/Users/abcd/cityeye-ai/diagnostics/camera3-calibration/before-overlay.jpg`

Supporting artifacts in the same directory: raw frame copies, before-geometry.json, calibration-report.json, observation.json, sampled annotated/raw images, recorded-configs.json, recorded-smoke.json, browser-regression.json and live-ui.png. They contain no RTSP credentials or secrets.

Regenerate from the existing fresh local preview (no direct camera connection, no config writes):

```sh
cd /Users/abcd/cityeye-ai
ai/.venv/bin/python scripts/camera3-calibration.py
```

Files changed by P0 #3: `ai/config/live_camera.json`, `ai/calibration.py`, `ai/event_pipeline.py` (rule availability only; persistence unchanged), `ai/process_video.py`, `ai/tests/test_calibration.py`, `scripts/camera3-calibration.py`, this report and local diagnostic artifacts. Other uncommitted files are earlier work.

## 17. Remaining work / limitations

A clear **current** road-facing Camera 3 view is required to finish the actual polygons. The legal/expected flow must be established from camera-specific evidence or an operator's confirmation, not inferred from image appearance or the old generic arrows. Then fill the Camera 3 profile's pixel polygons/direction, mark only evidence-backed confirmations true, regenerate the overlay, restart the worker and repeat observation. Changing camera angle can invalidate geometry even at the same resolution; this guard cannot infer camera pose from pixels.

Stopped's prior-motion → duration → one proposal → rearm behavior and its 8-second live duration remain unchanged. Congestion thresholds remain 16 vehicles (moderate 12), density 0.04, spacing/movement 0.12 and duration 5 seconds. Their suitability cannot be judged until a useful road ROI exists; they were not silently tuned. No real-world lane precision, event validation, or completed P0 #3 calibration is claimed.
