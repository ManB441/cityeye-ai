# Maydan Palestine — calibration and validation

## Outcome

Recorded video analysis and staged browser playback PASS. Road and stopped polygons are configured at native 1024×576 resolution. Wrong Way and Congestion are explicitly disabled; traffic remains UNKNOWN. No positive incident validation or deployment is claimed.

## Source and alignment

- Local source: `ai/sample_videos/maydan_palestine.mp4` (RECORDED DEMO).
- Source SHA-256: `0c089a536c0f4d1b690c92a42023202a9ece7b8232302e16e9fb87354618cc2d`.
- Resolution 1024×576; 20 FPS; 6,243 frames; 312.15 seconds.
- Source, analyzed MP4 and H.264 browser MP4 share frame count, resolution and FPS.
- All 6,243 timeline observations match frame number and video time (frame / 20).
- Seven same-frame source/output comparisons passed; visual inspection of detection overlays at 60s and 300s confirms the same scene. Boxes/text introduce expected pixel differences.

## Geometry and enabled rules

Road (enabled): `[[390, 245], [620, 185], [750, 215], [735, 275], [810, 323], [720, 430], [550, 438], [435, 348], [310, 305]]`.

Stopped (enabled): `[[430, 260], [610, 220], [700, 240], [710, 300], [660, 360], [540, 365]]`.

These polygons deliberately cover only central intersection asphalt and exclude buildings, sidewalk, islands, crosswalk stripes and the signal queues. They are not invented lane boundaries. Points representing non-road/queue areas are excluded in regression tests. Reference frames at 0/30/60/120/180/240/300 seconds show a stable camera angle.

Stopped duration remains 60 seconds; no algorithm/threshold changes. No qualifying stopped proposal occurred, so stopped-vehicle positive acceptance remains NOT VALIDATED. Wrong Way is disabled because a single upward direction is invalid for multiple intersecting/turning movements. Congestion is disabled because central occupancy has not been calibrated as queue density. Road blockage remains disabled.

The explicit recorded profile uses the existing geometric validation plus a source hash check before processing. Wrong source bytes, camera identity or resolution are rejected/disabled safely. Existing recorded scenarios without an explicit profile and current valid live profiles retain their behavior.

## Actual detection and tracking evidence

- 52689 detection/track rows; 52626 vehicle observations.
- 712 distinct vehicle IDs: these are not unique traffic throughput and may include fragmented identities.
- Vehicle confidence range 0.25–0.9534.
- 3696 vehicle observations inside the road ROI; 48930 outside; 1757 inside the stopped ROI, evaluated by the trajectory-center convention.
- Zero events. All timeline traffic states UNKNOWN, as intended.

Detection is not perfect: the clear foreground white car at 60s has no box, and a farther yellow van is labeled car. Detection/tracking PASS means real outputs exist, not exhaustive recall or stable identity certification. The model and tracker were not altered. Outside-ROI detections remain visible and count toward frame-wide totals; ROI gating affects event relevance.

## API and browser compatibility

Isolated backend against the actual new artifacts: timeline HTTP 200 / 6,243 frames, events and summary HTTP 200; MP4 range request HTTP 206 with exact matching 4,096 bytes. Browser artifact is H.264/yuv420p with fast-start metadata, 6,243 frames at 20 FPS. This verifies codec/metadata and serving; it is not a manual test of every browser. Test database and no-auth settings were isolated; production authentication and database were untouched.

231 AI tests passed. Includes geometry/source/resolution/identity regressions and existing event/worker tests. Detection model, confidence, image size, IoU and event thresholds match the prior configuration. Other scenario configurations and Camera 3 geometry were not edited.

## Limits and publication

Latitude/longitude 0,0 remain unverified placeholders; no geographic location is claimed. Person/bicycle road-membership fields remain unavailable with the current congestion dependency, while frame-wide detections continue. Existing served artifacts were preserved; this run, browser conversion and source changes are staged, not deployed. No synthetic or recorded incidents were inserted into production.

Local files: `annotated-browser.mp4`, `calibrated-run/`, `frame-*.jpg`, `overlay-*.jpg`, `yolo-roi-*.jpg`, validation JSON, API metadata and test logs. Publish the matched artifact set together after deployment; never mix this timeline with the old video.
