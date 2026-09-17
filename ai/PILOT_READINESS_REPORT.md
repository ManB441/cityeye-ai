# CityEye AI Stopped Vehicle and Wrong-Way Pilot Report

## Scope and decision

This work changes event reasoning, evidence metadata, and validation only. It does not change the YOLO model, retrain detection, tune general recall, redesign the frontend, or add unrelated event types.

Stopped Vehicle is validated on the supplied real scenario. Wrong-Way has stronger rule/config architecture and synthetic regression coverage, but it is not claimed as real-video validated because the repository contains no suitable wrong-way or reversing-road clip.

## 1. Previous stopped-vehicle logic

- Speed was the center-point displacement between consecutive tracked observations divided by elapsed video seconds, in pixels/second.
- Stationary duration accumulated while that instantaneous speed remained below a threshold and reset on movement or an observation gap longer than 1.0 second.
- The rule required a stable ByteTrack ID, at least 5 observations in the stopped scenario, current center-point membership in the monitored polygon, and the configured duration.
- ROI membership used point-in-polygon on the tracked box center.
- Duplicate suppression permanently remembered an emitted track ID, so the same track could never create a second legitimate stopped episode.

## 2. Previous stopped threshold

The stopped scenario used 80 px/s, 2.5 seconds, 5 track observations, and a 1.0-second maximum observation gap. The 80 px/s value was camera/resolution dependent and could not be described as physical speed.

## 3. New stopped movement strategy

- Normalize center movement by the monitored road ROI diagonal (`ROI diagonals/second`).
- Smooth normalized speed with a configurable rolling median to reduce detector-box jitter.
- Require both the smoothed value to be below the stopped threshold and the instantaneous value to remain below a separate release/guard threshold. This prevents a stale low median from confirming a moving vehicle.
- Permit a camera-specific `stopped_vehicle_polygon`, separate from the broad traffic ROI, so moving traffic in other lanes cannot satisfy the stopped-road-zone condition.
- Keep raw pixel speed only as a debug measurement; the system does not claim km/h.
- Suppress duplicates for the active stopped episode. Rearm the same track only after sustained movement above the release threshold.

## 4. New stopped configuration

For the supplied 1280x720 stopped-vehicle scenario:

- active stopped zone: `[[150,380],[1120,380],[1120,650],[150,650]]`
- stopped threshold: `0.08 ROI diagonals/second`
- movement release/instantaneous guard: `0.18 ROI diagonals/second`
- rolling median window: 15 observations
- stationary duration: 1.5 seconds (short demonstration clip only)
- rearm movement duration: 1.0 second
- minimum observations: 5
- maximum observation gap: 1.0 second

The 1.5-second duration is calibrated for this short staged clip and should not be copied blindly to a live municipal camera. A live pilot should start conservatively (for example 5-10 seconds), then be calibrated from reviewed camera-specific data.

## 5. Stopped event validation

The final full-video run processed 318 frames and 1,640 road-user track records. It created exactly one `STOPPED_VEHICLE` event:

- target track ID: 7
- class: car
- trigger: frame 120, video time 4.000 seconds
- stationary duration at confirmation: 1.500 seconds
- smoothed normalized movement: 0.020433 ROI diagonals/second
- instantaneous normalized movement: 0.015230 ROI diagonals/second
- raw debug speed at confirmation: 15.811 px/s
- confidence: 0.9234
- review state: `PROPOSED`

Representative raw center/speed samples near confirmation include frame 102: 0.0 px/s, frame 103: 21.213 px/s, frame 104: 15.0 px/s, frame 111: 0.0 px/s, and frame 120: 15.811 px/s. Larger one-frame box shifts occurred, which is why temporal smoothing plus an instantaneous guard are both used.

The evidence image was visually reviewed: track 7 covers the disabled red foreground car. A prior candidate event on moving background track 399 was rejected by introducing the dedicated stopped zone; a prior candidate on track 155 was rejected by the instantaneous movement guard.

## 6. Duplicate suppression

The final run produced one event, not one event per frame. Unit coverage confirms repeated evaluation of the same stopped episode emits once. It also confirms that sustained motion rearms the track and allows one new event for a later valid stopped episode.

## 7. Previous wrong-way configuration

The geometry compared track displacement with one global allowed vector (`start -> end`) using cosine opposition. The demo scenario values were effectively disabled:

- minimum displacement: 10,000 px
- minimum trajectory points: 30
- directional confidence: 0.95
- no multi-observation persistence requirement beyond accumulated trajectory

The available demo clips therefore do not trigger Wrong-Way by design.

## 8. New wrong-way configuration architecture

`direction_zones` can now define multiple polygons, each with its own name and allowed vector. A tracked vehicle is evaluated only against the direction rule for its current zone. The provided example starts with:

- normalized displacement: 0.04 of zone diagonal
- minimum points: 6
- minimum consecutive opposite evaluations: 4
- directional confidence: 0.80

These are example starting values, not a production calibration. They must be calibrated against a real camera and a suitable wrong-way clip.

## 9. Wrong-way trajectory logic

For contiguous observations inside a direction zone, the rule calculates the track displacement vector and normalizes displacement by the zone diagonal. It calculates cosine agreement with the configured allowed vector; a strong negative cosine is opposite movement. The event requires sufficient points, meaningful normalized displacement, strong opposition, and repeated opposite evaluations. Small jitter, allowed-direction travel, weak diagonal movement, and long observation gaps reset or fail the candidate. One event is emitted per active track.

Structured event details include track ID/class, pixel and normalized displacement, direction score, measured vector, allowed vector, zone name, ROI state, evidence path, and review state.

## 10. Wrong-way trigger test result

Synthetic geometry/regression tests pass for opposite travel, allowed travel, normalized scale independence, minimum history, minimum displacement, repeated opposite observations, direction confidence, diagonal travel, observation gaps, outside-zone travel, and one-event deduplication.

No exact real-video trigger timestamp or real wrong-way evidence is reported. There is no suitable wrong-way/reversing clip in `ai/sample_videos`, so creating such a result would be fabricated.

## 11. Wrong-way false-positive checks

Automated tests confirm no event for normal direction, small jitter, insufficient history, insufficient displacement, weak/diagonal opposition, tracks outside the zone, and trajectories split by a long detection gap. Zone-specific direction configuration works without requiring a misleading global direction vector.

## 12. Evidence

- Stopped Vehicle: real annotated JPG generated at frame 120 / 4.00 seconds, with bounding box, track ID, frame number, timestamp, and vehicle count.
- Wrong-Way: no real JPG generated because no honest real-video validation clip exists.
- Development-only visualization can display track paths, normalized movement, stationary duration, allowed direction arrows, measured trajectory arrows, and opposition score. It is disabled by default with `debug_event_analysis: false`.

## 13. Files changed

- `ai/trajectory.py`
- `ai/event_rules.py`
- `ai/event_pipeline.py`
- `ai/events.py`
- `ai/process_video.py`
- `ai/config/camera.json.example`
- `ai/config/wrong_way_zones.json.example`
- `ai/tests/test_stopped_vehicle.py`
- `ai/tests/test_wrong_way.py`
- `ai/tests/test_event_pipeline.py`
- `backend/app/schemas.py`
- `backend/app/database.py`
- `backend/tests/test_database.py`
- local ignored scenario configuration/output for `stopped_vehicle`

Existing untracked P0 evaluation files were preserved and not modified as part of this task.

## 14. Regression results

- AI: 138 passed
- Backend: 112 passed
- Frontend: 6 passed
- TypeScript + Vite production build: passed
- Python compilation: passed
- `git diff --check`: passed

Existing congestion, person, bicycle, motorcycle, tracking, frontend, and API tests remain green. The optional structured `details` field is persisted through SQLite, including migration of an existing events table. Legacy events omit the field rather than changing their wire shape to `details: null`.

## 15. Remaining limitations and priorities

- **P0:** none for demonstrating the validated Stopped Vehicle scenario.
- **P1:** obtain and manually review a representative real wrong-way clip before presenting Wrong-Way as pilot-validated. Calibrate each lane/zone vector and thresholds on that camera.
- **P1:** calibrate a longer stopped duration and polygon per real municipal camera; the 1.5-second value is only for the short staged clip.
- **P2:** collect reviewed false-positive/false-negative event labels per camera and tune normalized thresholds from distributions rather than one clip.
- **P2:** add short evidence clips if the existing storage architecture later supports them; this task intentionally stores the confirmation JPG only.
- **P3:** perspective-aware road-plane calibration could improve movement normalization, but it requires camera calibration data and is outside this MVP.

Wrong-Way should remain disabled in the current demo scenarios until the P1 real-video validation is complete.
