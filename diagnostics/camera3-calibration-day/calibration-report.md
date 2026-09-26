# Camera 3 daylight calibration — P0 #3.6

Road and stopped geometry are enabled in the existing Camera 3 profile. Wrong Way remains disabled. Detection, tracking and road ROI have direct live evidence; stopped-vehicle and congestion incidents have NOT been validated. No YOLO, ByteTrack, thresholds or event algorithms changed.

## CAMERA
944×1080, current live DVR Camera 3 RTSP through existing VLC/OpenCV pipeline. Reference observed 2026-09-18T11:16:56.642652+00:00, generation 5. See [reference](calibration-frame.jpg) and [overlay](calibration-overlay.jpg). Fresh daytime image, not old nighttime calibration. DVR OSD time differs from host time.

## ROAD ROI
ENABLED. Conservative interior of visibly identifiable asphalt, excluding upper parking forecourt, left frontage, right building/steps, and near cropped foreground. Not a survey of lanes or entire road width.

Coordinates (x, y): `[[515, 105], [610, 110], [638, 205], [595, 320], [525, 450], [390, 700], [95, 700], [80, 570], [180, 400], [355, 225]]`.

## STOPPED VEHICLE
ENABLED. Inset roadway section where a vehicle obstructing travel is relevant; contained by road polygon and excludes off-road parking. Existing require_prior_motion=true remains mandatory. Geometry enabled; incident sequence not demonstrated.

Coordinates (x, y): `[[385, 260], [570, 255], [520, 400], [380, 610], [170, 610], [235, 440]]`. Existing duration 8 seconds; prior motion required. No event is justified simply because a vehicle is already stationary.

## WRONG WAY
DISABLED. Direction vector: none; direction zones: empty. Geometry shows a road axis but does not establish legal travel direction. Observed vehicle travel alone is not legal-direction evidence.

## CONGESTION
Clearly identifiable conservative road polygon enables existing congestion rule only; no thresholds changed. Positive congestion-event behavior remains unvalidated. Rule ENABLED; positive-event validation NOT VALIDATED. Full-image vehicle counts can include parked vehicles outside the ROI; congestion uses its own ROI-filtered count.

## VALIDATION

### DETECTION: PASS
Visible cars detected, not exhaustive recall validation
- live-observation/frame-5885.jpg: car #355 0.90, #359 0.89; parked #163 0.78 and #3 0.55.
- live-observation/frame-6186.jpg: car #386 0.86 and #377 0.85.
- live-observation/frame-6192.jpg: #386 0.93 and #377 0.77.

Large silver foreground vehicle visibly present without a published detection box in these frames. This task does not identify whether absence originates in detector, tracker or filtering. Do not treat NORMAL as proof of an unobstructed road.

### TRACKING: PASS
Live production IDs across successive observations
- frame-6186.jpg -> frame-6192.jpg: IDs 386 and 377 persist while their positions change. Parked IDs 163 and 3 remain visible.

Not a long-duration identity-switch or recall evaluation.

### ROI: PASS
Visual geometry plus real production inclusion/exclusion
- frame-5466.jpg: two parked tracked cars outside polygon, production ROI count 0.
- frame-5885.jpg: four detected cars, production ROI count 1, density 0.184; interior car #359 included; off-road parked detections excluded.
- frame-6186.jpg: five detected cars, production ROI count 2, density 0.345.
- frame-6192.jpg: production ROI count 2, density 0.296.

Only conservative central roadway monitored. Production uses detection/track centers; a vehicle partially intersecting the polygon can be excluded if its center lies outside. No claim of full-lane coverage.

### STOPPED_VEHICLE: NOT VALIDATED
No documented naturally observed tracked MOVES -> in stopped ROI -> stationary for configured 8 seconds -> ONE proposed event sequence. Foreground vehicle already present in this observation cannot be used as a positive stopped test. No fake live event created.

### WRONG_WAY: NOT VALIDATED
Disabled: road geometry and observed motion do not establish a unique legally permitted direction. No direction vector or real-camera incident generated.

### CONGESTION: NOT VALIDATED
Calibrated road enables existing metric/rule computation. Selected frames show NORMAL and ROI counts 0/1/2. No sustained congestion scenario observed; thresholds were not tuned or validated for event sensitivity. NORMAL is detector-derived, not guaranteed physical traffic truth.

## Controlled live observation
355 production samples over 179.7s, 2026-09-18T11:55:16.362805+00:00 to 2026-09-18T11:58:16.050932+00:00; frames [5466, 7610]. Vehicles [1, 5]; tracks [1, 6]; traffic states ['NORMAL']; health ['ONLINE'].

See [observation metadata](live-observation/observations.json), [ROI 1 evidence](live-observation/frame-5885.jpg), [ROI 2 evidence](live-observation/frame-6186.jpg), [same tracks next frame](live-observation/frame-6192.jpg), and [parked exclusion](live-observation/frame-5466.jpg). These are actual production frames, not replay. Bounding box confidence text is rounded to two decimals. JPEG and JSON files read sequentially and can differ by one publication. Exact frame-specific ROI counts and IDs cited above come from the same annotated image, not a join to neighboring JSON.

No new event IDs appeared in the validation window. The pre-existing PROPOSED Wrong Way event `70197f71-3dce-4982-9c22-7ddb5e8164ba` was preserved and is not validation evidence.

## Activation and safety
User explicitly requested leaving daylight calibration enabled. There is NO automatic nighttime guard. **Manual disable before night is required.** Set camera_calibrations.camera-3.road_confirmed=false and stopped_confirmed=false in ai/config/live_camera.json, then restart only Camera 3 worker. This disables road-dependent rules and returns traffic to UNKNOWN. Do this before nighttime operation. Restore flags only after confirming daylight and unchanged camera position/resolution.

CALIBRATION_REQUIRED is expected because Wrong Way remains intentionally uncalibrated; road/stopped/congestion individually READY.

218 AI tests passed in 18.20 seconds; git diff --check passed. Updated actual Camera 3 profile integration assertion and tested ROI inclusion/exclusion with synthetic observations; synthetic test is not claimed as real-camera validation. Existing stopped prior-motion regression tests passed.

Hash checks confirm calibration validator, process worker, event pipeline/rules, trajectory logic and ByteTrack configuration are unchanged from task baseline. All non-camera-calibration configuration is identical. No temporary production instrumentation was added; diagnostic capture remains disabled. No commit/push.

## Next action
During daylight observe and preserve one naturally occurring detected/tracked moving-to-stopped sequence in the stopped ROI. Investigate the foreground vehicle missing from published detections separately before relying on stopped/congestion alerts.

## Final status
- ROAD ROI: PASS
- STOPPED VEHICLE: NOT VALIDATED
- WRONG WAY: NOT VALIDATED (disabled)
- CONGESTION: NOT VALIDATED
- DETECTION: PASS (visible cars; incomplete recall)
- TRACKING: PASS (observed persistent live IDs)
