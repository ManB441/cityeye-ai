# CityEye UI capability map

## Real now

- Four municipality demo scenarios returned by `GET /api/scenarios`.
- Processed scenario MP4, analysis summary, and video-synchronized timeline.
- Scenario events, evidence images, and municipal Verify/Dismiss decisions.
- Authentication with OPERATOR, REVIEWER, and ADMIN roles.
- Backend readiness status.
- Citizen report storage, listing, and community-confirmation status.

## UI only / future

- Historical traffic-volume and peak-hour analytics.
- Congestion forecasting.
- Multi-camera road-segment correlation.
- Geographic map tiles and camera/report marker visualization.
- Live-camera controls until the live-camera API is merged and configured.

## Missing

- Historical aggregation API.
- Historical storage must persist timestamped per-source class counts,
  density/status, source heartbeat/uptime, and event state transitions, with
  retention plus hourly/daily aggregation jobs.
- Forecasting model/API.
- Multi-camera calibration/correlation API.
- A map provider and geospatial display layer.
- A live-camera endpoint on the current PR #29 base.

Future surfaces must remain labelled `DATA COLLECTION REQUIRED`, `CALIBRATION
REQUIRED`, or `NOT YET AVAILABLE` until those capabilities exist.
