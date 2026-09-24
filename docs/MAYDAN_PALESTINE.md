# Maydan Palestine recorded calibration

This is a RECORDED DEMO, not a live camera. The inspected local video is 1024×576, 20 FPS, 6,243 frames (312.15 seconds). Seven reference frames at 0, 30, 60, 120, 180, 240 and 300 seconds show a fixed camera overlooking a signalized intersection with multiple turning paths.

## Configuration

`ai/config/scenarios/maydan_palestine.json` is now versioned; videos, weights and generated artifacts remain local. The opt-in `recorded_calibration` profile uses existing geometry checks and binds the calibration to the exact source SHA-256, camera identity and resolution. A replacement source fails validation before outputs are created. Legacy recorded scenarios without this explicit profile remain unchanged.

- Road ROI: conservative central intersection interior, excluding buildings, sidewalks, islands, crosswalk stripes and signal queues. This intentionally does not cover every visible road approach.
- Stopped ROI: a smaller central polygon where a stationary vehicle obstructs intersection travel, excluding the visible waiting queues. Existing duration remains 60 seconds. Enabling the ROI does not constitute positive stopped-event validation.
- Wrong Way: disabled. The single old upward vector was unsupported for a multi-direction signalized junction; allowed legal directions cannot be inferred from vehicle motion alone.
- Congestion: disabled, traffic status UNKNOWN. A central intersection ROI is not a validated approach-queue density region; existing thresholds were not tuned or activated.
- Road blockage: disabled, no calibrated blockage/upstream-impact zone.

Detection boxes and overall counts remain frame-wide. The polygons constrain spatial rules; they do not hide out-of-ROI detections or redefine counts as unique traffic throughput. With congestion disabled, the existing person/bicycle road-membership diagnostics remain unavailable; these detections still contribute to frame-wide class counts.

The existing latitude/longitude 0,0 values are unverified placeholders, not a geographic location. No map location or driving direction was invented. No new map feature was introduced.

## Reproduction

Place the original local video at `ai/sample_videos/maydan_palestine.mp4` and use the existing AI environment/model. Run from repository root:

```sh
ai/.venv/bin/python ai/process_video.py \
  --config ai/config/scenarios/maydan_palestine.json \
  --output-dir diagnostics/maydan-palestine/calibrated-run
```

The source hash is intentionally strict. Do not edit it to bypass a mismatch; inspect and recalibrate any replacement video first. The output is staged separately from the served scenario folder so the existing playback is not replaced during validation. OpenCV's MPEG-4 output may require H.264 conversion for browser playback; the diagnostic run includes a separate browser-compatible file when conversion is verified.

## Local evidence and publication

Reference frames and road/stopped overlays are in `diagnostics/maydan-palestine/`. These show existing pixels at native resolution; no coordinates were derived from memory or another camera. The final report records actual analyzed-frame counts, detection/track observations, source/output resolution and timing, rule states, tests, and any unvalidated event behavior.

This task stages source/configuration and analysis results. It does not rebuild or deploy the running backend/frontend, replace existing served scenario artifacts, or insert demo incidents into the production database. Publish the validated artifact set together during deployment; do not mix a new timeline with an old annotated video.
