# CityEye AI pipeline audit and evaluation report

Date: 2026-09-10  
Scope: current local MVP pipeline and the four dashboard scenarios. No production
weights, thresholds, event logic, API contracts, or frontend behavior were changed.

## 1. Current pipeline architecture

The active path is scenario JSON -> `process_video.py` -> Ultralytics YOLO tracking
with ByteTrack -> class-specific confidence filters -> trajectory history -> ROI and
event rules -> `tracks.csv`, `events.json`, annotated MP4, and JPG evidence -> FastAPI
scenario endpoints -> Municipal Dashboard polling and video playback.

`ai/config/camera.json` is not the dashboard source of truth. The four files under
`ai/config/scenarios/` are the active configurations for generated dashboard data.

## 2. Active model and tracking stack

- Production detector: COCO-pretrained `yolov8n.pt`.
- Road-user classes: person, bicycle, car, motorcycle, bus, truck.
- Tracking: Ultralytics `model.track(..., persist=True)` with ByteTrack.
- ByteTrack settings: high/new-track 0.22, low 0.10, buffer 30, match 0.80,
  fused confidence score enabled.
- Runtime measured here: Python 3.13.14, Ultralytics 8.4.121, Torch 2.13.0,
  OpenCV 5.0.0, Apple arm64 CPU. CUDA and MPS were unavailable.

## 3. Detection thresholds and image sizes

- Normal and congestion: detector size 1280, vehicle threshold 0.25, IoU 0.70.
- Rain and stopped vehicle: detector size defaults to 960, vehicle threshold 0.40,
  IoU defaults to 0.70.
- Person and bicycle thresholds default to 0.22 where not overridden.
- Lowering only the raw inference threshold from the production floor to 0.05 did
  not increase accepted detections in the normal or congestion samples because the
  class-specific production filters rejected the additional raw boxes.

## 4. Preprocessing and ROI handling

Production inference uses the full decoded frame; there is no resize/crop stage before
Ultralytics other than its normal letterbox preprocessing. Vehicle congestion ROI uses
the box center. Person and bicycle road-membership use bottom-center, which is more
appropriate for ground contact. The benchmark's D variant crops to the bounding
rectangle of the configured road polygon and maps boxes back to source coordinates.

## 5. Trajectory analysis and event generation

Track histories contain center positions and timestamps. Pixel speed is center
displacement divided by elapsed time. Histories reset their stationary accumulation
after motion or an observation gap above one second.

- Congestion combines accepted vehicle count, perspective-weighted occupied area,
  nearest-neighbor spacing, normalized movement, persistence, and release grace.
- Stopped vehicle requires a stable tracked ID, ROI membership, minimum observations,
  low speed, and sustained stationary duration.
- Wrong way compares sustained track displacement to one configured allowed vector.
- Rules emit once per active condition/track; each emitted event receives an actual
  annotated JPG evidence image and a UUID. Backend ingestion rejects duplicate UUIDs.

## 6. Existing output audit

The current generated outputs contain:

- Normal: 372 frames, 5-19 tracked road users/frame (12.03 average), no event.
- Congestion: 407 frames, 19-39 vehicles in ROI/frame (28.66 average), one congestion
  event at 5.0 s with 24 vehicles and density 0.176.
- Rain: detections in 611 frames, 1-6 tracked road users/frame where present, no event.
- Stopped: 318 frames, 1-5 vehicles in ROI/frame (2.52 average), one stopped event at
  10.167 s for track 1 after 2.5 s; no duplicate event was emitted.

The stopped scenario's threshold is 80 px/s, and its event was emitted while the track
reported 75 px/s. This is internally consistent but permissive; it requires manual
validation before being described as a generally reliable stopped-vehicle threshold.

## 7. Representative benchmark results

Three timestamps per scenario were evaluated. Counts below are totals across those
three independent frames after production class-specific confidence filtering.
Isolated-frame benchmarking does not run ByteTrack; tracking quality comes from the
full-video output audit above.

### Normal traffic

- A production: 40 accepted detections, about 9.21 FPS.
- B YOLOv8n/1280/raw conf 0.05: 40, about 9.33 FPS.
- C YOLOv8s/1280/full: 50, about 4.63 FPS.
- D YOLOv8s/1280/road crop: 47, about 6.37 FPS.

### Heavy congestion

- A: 115 accepted detections, about 9.15 FPS.
- B: 115, about 9.12 FPS.
- C: 159, about 4.62 FPS.
- D: 164, about 4.86 FPS.

YOLOv8s increased accepted detections substantially here, including motorcycles, but
these are not yet verified true positives.

### Rain

- A: 6 accepted detections, about 16.46 FPS at production size 960.
- B: 6, about 9.16 FPS at size 1280.
- C: 9, about 4.51 FPS.
- D: 9, about 4.50 FPS because the configured ROI covers the whole portrait frame.

### Stopped-vehicle clip

- A: 22 accepted detections, about 16.45 FPS at production size 960.
- B: 21, about 9.29 FPS.
- C: 22, about 4.54 FPS, including three motorcycle classifications.
- D: 18, about 5.29 FPS. Its crop changed context and class distribution materially.

These FPS values are detector-only, after an untimed warm-up. Full pipeline FPS will
be lower because decoding, tracking, drawing, CSV/JSON, and video encoding are excluded.

## 8. Ground-truth and accuracy status

No manually annotated frames were present. Consequently TP, FP, FN, precision, recall,
and class confusion are intentionally reported as unavailable. The harness calculates
them only when explicit same-frame annotations are supplied. Higher box count is not
treated as higher accuracy.

Manual annotation should start with the exact benchmark frames:

- normal traffic: frames 50, 175, 300;
- congestion: frames 60, 180, 300;
- rain: frames 120, 360, 599 (rounded from timestamps using source FPS);
- stopped vehicle: frames 60, 150, 240.

Annotate all six road-user classes, including partially occluded and small distant
objects, in source-frame pixel coordinates. Add extra frames around the stopped event
(approximately frames 302-308) to validate event causality.

## 9. Congestion validation

The current normal clip emits no congestion event; the congestion clip emits one event
after the configured five-second persistence window. This is the correct scenario-level
separation in the existing sample set. The rule does not require low movement in its
high-count branch: `count >= min_vehicles` plus either density or close spacing can
start congestion. Movement is required only by the moderate-count branch.

Potential calibration issue: scenario files that set `congestion_min_vehicles` to 99
but omit `congestion_moderate_min_vehicles` inherit a moderate threshold of 12. They
cannot emit a heavy event within these short clips, but the live state may still show
MODERATE. If the intention is to disable congestion entirely, both thresholds should
be explicit or an enable flag should be added in a separate production change.

## 10. Stopped-vehicle reliability

The current stopped clip produced one evidence-backed event for one stable track and
suppressed repeats for that track. The rule is structurally sound, but the 80 px/s
threshold is camera-scale dependent and far above the generic 3 px/s default. It should
be calibrated per camera or normalized by frame/ROI scale before production claims.

## 11. Wrong-way readiness

Wrong-way logic exists and has unit coverage for valid, invalid, and insufficient
trajectories. All four demo scenario configs effectively disable it using a 10,000 px
minimum displacement, 30 points, and 0.95 directional confidence. There is no
direction-labeled test clip and no lane-specific direction model. It is therefore
implemented but not production-calibrated or demonstrated.

## 12. Event quality and evidence

Events currently include type, timestamp, confidence, severity, explanation, camera,
coordinates, evidence path, and review status. Congestion count/density and stopped
track/speed/duration exist only inside human-readable explanation text, not as structured
fields. This weakens downstream analytics and should be corrected after evaluation.
Evidence files are genuine frames from the processed video, not placeholders.

## 13. Debugging support

The production pipeline already logs periodic traffic count, ROI count, tracked count,
density, spacing, movement, candidate duration, and state when debug mode is enabled.
The new `evaluation.py` adds repeatable JSON output summaries, detector variants,
per-class raw/filtered/ROI counts, timing, and optional ground-truth quality metrics.
It remains separate from production behavior.

## 14. Regression status

- Backend: 110 tests passed.
- AI pipeline including the new harness: 126 tests passed.
- Frontend: 6 tests passed.
- TypeScript/Vite production build passed.
- Evaluation harness unit tests: 7 passed.

## 15. Risks and limitations

- No ground truth means detector precision/recall and event accuracy are unknown.
- All evaluation clips are short and four scenarios are not representative coverage.
- The same clips used for tuning are also the current demonstration clips.
- ByteTrack quality was not benchmarked against manually annotated identities.
- Pixel-speed thresholds are resolution/camera dependent.
- One global allowed direction cannot model bidirectional or turning lanes.
- Detector throughput on this CPU is below source video frame rate.
- Rain detection is weak in the sampled frames.
- Bicycle detections remained zero in all 12 benchmark frames.

## 16. Recommended next task

**P0: create and review a small frozen ground-truth set before any production tuning.**

Annotate the 12 listed frames plus stopped-event-adjacent frames, then run A/B/C/D with
the provided harness. Select the model/crop only by per-class precision/recall and event
behavior, with special attention to bicycles, motorcycles, distant vehicles, and rain.

After P0:

- P1: calibrate per-camera ROI/direction and normalized stopped thresholds.
- P1: add one real direction-labeled wrong-way clip and identity annotations.
- P1: make event measurements structured fields and add temporal event assertions.
- P2: evaluate frame skipping or asynchronous inference for usable dashboard latency.
- P3: consider fine-tuning only if the frozen evaluation set proves COCO weights are
  insufficient; do not train before collecting representative labeled data.

## 17. Reproduction commands

See `ai/EVALUATION.md`. Machine-readable reports were generated under `/private/tmp`
during this audit so benchmark artifacts do not pollute the repository. The empty
`evaluation_ground_truth.example.json` is a schema starting point, not ground truth.

## 18. Production decision

No production model or threshold change is justified yet. Variant D is the most
promising next candidate for high-resolution landscape congestion because it recovered
more accepted detections than production at roughly half production detector FPS, while
being faster than full-frame YOLOv8s. It must pass the frozen manual ground-truth set
before adoption. For full-frame portrait rain, cropping gives no benefit.
