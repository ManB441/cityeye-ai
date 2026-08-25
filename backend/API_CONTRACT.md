# CityEye AI MVP API Contract

This contract fixes the field names and endpoint names used by the AI,
Backend, and Frontend. Endpoints marked as planned are implemented in later
Backend tasks.

## Event fields

Every AI event submitted to the Backend contains:

```json
{
  "event_id": "unique-event-id",
  "event_type": "WRONG_WAY",
  "timestamp": 12.5,
  "confidence": 0.91,
  "severity": "HIGH",
  "explanation": "Track 7 moved opposite to the allowed direction.",
  "camera_name": "Demo Camera 1",
  "latitude": 31.95,
  "longitude": 35.91,
  "evidence_image": "evidence/event_0001_wrong_way.jpg",
  "status": "PROPOSED"
}
```

Allowed values:

- `event_type`: `WRONG_WAY`, `STOPPED_VEHICLE`, `CONGESTION`
- `severity`: `LOW`, `MEDIUM`, `HIGH`
- `status`: `PROPOSED`, `VERIFIED`, `DISMISSED`

AI ingestion accepts only `PROPOSED`. `VERIFIED` and `DISMISSED` are municipal
human decisions.

## Local storage

Events are stored in one local SQLite database. The database file is generated
at runtime and must not be committed. Event IDs are unique, and duplicate AI
submissions are rejected instead of creating duplicate dashboard events.

## Endpoint names

Currently implemented:

- `GET /health`
- `GET /api/analysis/summary`
- `GET /api/analysis/timeline`
- `GET /media/annotated.mp4`
- `POST /api/events/ingest`
- `GET /api/events`
- `GET /api/events/{event_id}`
- `POST /api/events/{event_id}/verify`
- `POST /api/events/{event_id}/dismiss`
- `GET /evidence/{filename}`
- `GET /api/scenarios`
- `GET /api/scenarios/{scenario_id}/analysis/summary`
- `GET /api/scenarios/{scenario_id}/analysis/timeline`
- `GET /api/scenarios/{scenario_id}/events`
- `POST /api/scenarios/{scenario_id}/events/{event_id}/verify`
- `POST /api/scenarios/{scenario_id}/events/{event_id}/dismiss`
- `GET /media/scenarios/{scenario_id}/annotated.mp4`
- `GET /evidence/scenarios/{scenario_id}/{filename}`

Evidence responses accept only a single `.jpg` or `.jpeg` filename inside the
configured evidence directory. They are returned with `Cache-Control: no-store`
and are intended for the municipal dashboard, not automatic citizen-map display.

The analysis summary reads the generated `tracks.csv`. In its last detection
frame it counts distinct assigned `track_id` values plus each unassigned
detection row, so real detections are not hidden while ByteTrack is assigning
an ID. Missing or invalid output is reported explicitly without fabricated
counts. The media endpoint serves only the fixed generated `annotated.mp4`; it
never accepts a user-provided path.

The analysis timeline groups real `tracks.csv` rows by video frame and reports
active vehicle and class counts for synchronization with video playback. It does
not interpolate missing detections or replace YOLO class labels.

Citizen report endpoints will be documented when that task begins. They are
not part of the event-storage contract.

## Citizen report fields

Citizen report storage accepts:

```json
{
  "category": "CONGESTION",
  "description": "Traffic is moving very slowly.",
  "latitude": 31.95,
  "longitude": 35.91,
  "demo_user_id": "demo-user-1"
}
```

The Backend generates `report_id`, `reported_at`, and the initial `PENDING`
status. Supported categories are `CONGESTION`, `ROAD_HAZARD`, `BLOCKED_ROAD`,
and `OTHER`. `demo_user_id` identifies distinct demo submissions only; it is
not authentication or a personal user account.

Citizen report endpoints:

- `POST /api/citizen-reports`
- `GET /api/citizen-reports`
- `GET /api/citizen-reports/{report_id}`

Clients cannot submit `status`, `report_id`, or `reported_at`. Those values are
owned by the Backend.

A report cluster becomes `COMMUNITY_CONFIRMED` only when at least five distinct
`demo_user_id` values submit the same category within 100 meters and 15 minutes.
Repeated reports from one demo user count once. Incompatible reports remain
`PENDING`.

## Local demo data commands

`python -m app.demo_data seed` creates five clearly labeled Citizen Report
fixtures through the same repository and clustering logic used by the API.
`python -m app.demo_data reset` removes only reports whose `demo_user_id` starts
with `cityeye-demo-user-`. These are local CLI commands, not public API
endpoints, and they never create simulated AI events.
