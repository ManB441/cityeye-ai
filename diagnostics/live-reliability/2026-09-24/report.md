# T06 — Live preview and reconnection reliability

## Reproduced bugs and fixes

The frontend retry URL token also acted as its retry budget. Successful image loads did not restore the budget, so later independent outages escalated too soon to permanent ERROR; manual retry did not reset the automatic budget either. Three new regressions failed before the fix. Consecutive failures now have a separate counter, reset on successful load, manual retry and source/mode change. Existing 500/1000/2000 ms backoff and retry limit are unchanged. Each new stream URL mounts a fresh image element.

The raw preview route only checked camera health when opening the HTTP stream. A new endpoint regression demonstrated the absence of a continuing health check. The raw stream now uses the existing MJPEG currentness check every 250 ms to close on non-ONLINE state, expired heartbeat, invalid health, camera identity mismatch, reconnect generation change or changed connection timestamp. AI streams retain their existing freshness checks.

## Validation

- Backend: 252 tests passed, including current health/generation and existing stale-AI guards.
- Frontend: 80 tests passed, including recovery budgets for raw and AI views, manual recovery, source switching, old timer cleanup and existing stale-generation UI tests.
- Frame-source suite: 25 tests passed with controlled reconnect/capture conditions.
- TypeScript app/node checks and production build passed. Build output is `/tmp/cityeye-t06-build`; no deployment performed.

## Passive Camera 3 observation

120.24 seconds, 61 samples at 2-second intervals. All sampled states ONLINE. Generation remained 127. Reconnect counter remained 884; observed counter delta 0 over this interval, not a lifetime reliability claim. Reported dropped-frame counter delta 0; this is worker telemetry, not an independent packet-loss measurement.

Mean capture/preview/inference FPS: 12.03/10.95/3.95. No outage was induced on the user's only camera. No natural reconnect occurred, so real recovery latency is NOT OBSERVED. A two-minute sample does not establish long-duration reliability and does not validate deployment of the uninstalled patch.

## Limits and unchanged behavior

No changes to capture pipeline, YOLO, ByteTrack, event algorithms, calibration or thresholds. No worker restart or production DB write. Camera 3 remains daylight-only calibrated with the existing manual nighttime-disable requirement; transport ONLINE does not mean nighttime imagery is usable. T05 natural stopped-event validation is deferred at the user's request until suitable footage is available.
