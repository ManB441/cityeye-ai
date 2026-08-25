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
- `POST /api/events/ingest`
- `GET /api/events`
- `GET /api/events/{event_id}`
- `POST /api/events/{event_id}/verify`
- `POST /api/events/{event_id}/dismiss`
- `GET /evidence/{filename}`

Evidence responses accept only a single `.jpg` or `.jpeg` filename inside the
configured evidence directory. They are returned with `Cache-Control: no-store`
and are intended for the municipal dashboard, not automatic citizen-map display.

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
