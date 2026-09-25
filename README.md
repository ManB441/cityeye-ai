# CityEye AI — Competition MVP

For the current login, role permissions, secure runtime setup and validation
results, see [Secure access](SECURE_ACCESS.md). Some original milestone descriptions
below predate the current implementation.

Two-week MVP for a team of three developers. Proves CityEye AI can analyze real traffic video, detect and track vehicles, generate traffic events, and display results on a municipal dashboard and citizen map.

**This repository is intentionally simple** — no microservices, Redis, PostGIS, Docker, advanced auth, or custom model training.

## MVP scope

| Phase | Days | Deliverable |
|-------|------|-------------|
| Slice 1 | 1–3 | MP4 → YOLO detect/track → `annotated.mp4` + `tracks.csv` |
| **Slice 2 (current)** | 4–6 | WRONG_WAY, STOPPED_VEHICLE, CONGESTION events + evidence JPGs |
| Slice 3 | 7–9 | FastAPI + SQLite, Municipal Dashboard, Citizen Map |
| Slice 4 | 10–14 | Integration, demo data, UI polish, README rehearsal |

### Required features (full MVP)

- Video sources: local MP4, webcam, optional RTSP
- Pretrained lightweight YOLO (people, bicycles, cars, buses, trucks, motorcycles)
- ByteTrack (or YOLO built-in tracker)
- Events: WRONG_WAY, STOPPED_VEHICLE, CONGESTION
- React app: Municipal Dashboard + Citizen Traffic Map (Leaflet/OSM)
- Python, OpenCV, FastAPI, SQLite, 2-second API polling
- Configurable thresholds in JSON; road polygon + allowed direction in config

### Out of scope for the current AI slice

FastAPI backend, React UI, citizen reports, OCR, and authentication.

## Repository layout

```
cityeye-ai/
├── ai/           # Detection, tracking, events (Python)
├── backend/      # FastAPI + SQLite (Days 7–9)
└── frontend/     # React + TypeScript + Leaflet (Days 7–9)
```

## Slice 1 — Install and run

### Prerequisites

- Python 3.10+
- A traffic MP4 file (place at `ai/sample_videos/traffic.mp4` or pass `--video`)

### Setup

```bash
cd cityeye-ai/ai
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config/camera.json.example config/camera.json
```

Edit `config/camera.json` if your video path differs.

### Run detection, tracking, and event analysis

```bash
# Using path from camera.json
python process_video.py

# Or override video path
python process_video.py --video /path/to/your/traffic.mp4
```

### Optional pilot RTSP camera

The default `VIDEO_FILE` workflow above is unchanged. To run one selected live
camera, copy the example locally and provide the RTSP URL through an environment
variable so credentials never enter Git, API responses, or the browser:

```bash
cd cityeye-ai/ai
cp config/live_camera.json.example config/live_camera.json
export CITYEYE_RTSP_URL='rtsp://username:password@camera-host:554/stream'
source .venv/bin/activate
python process_video.py --config config/live_camera.json --output-dir live_output
```

The worker uses a latest-frame buffer, limits inference to `inference_fps`, and
reconnects with bounded exponential backoff. A reconnect creates a new stream
generation and resets ByteTrack plus temporal event state, preventing IDs,
motion history, and stopped/wrong-way timers from crossing a camera outage.
Live timestamps are Unix wall-clock seconds; video-file timestamps remain
relative seconds from the start of the file.

Live worker outputs are `ai/live_output/latest.jpg`, `camera_status.json`,
`live_metrics.json`, `events.json`, and `evidence/`. The Backend converts the
latest processed JPEG into an MJPEG response at `/media/live-camera.mjpg` and
exposes sanitized status, metrics, and events under `/api/live-camera/*`.
Only the server opens RTSP; the frontend never receives the camera URL or
credentials. Use a read-only camera account and isolate pilot cameras on the
municipal network or VPN.

### Outputs

| File | Description |
|------|-------------|
| `ai/output/annotated.mp4` | Input video with bounding boxes, class labels, track IDs |
| `ai/output/tracks.csv` | Per-frame road-user detections, tracking, person road-zone status, and possible rider association |
| `ai/output/events.json` | Real rule matches; an empty JSON list when no threshold is met |
| `ai/output/evidence/*.jpg` | Annotated evidence image for each generated event |

All AI events are saved with `PROPOSED` status for human review. Thresholds,
the monitored polygon, and the allowed road direction are configured in
`ai/config/camera.json`.

On first run, Ultralytics downloads `yolov8n.pt` (~6 MB) automatically.

## Backend — FastAPI skeleton

Create and activate a dedicated Backend environment:

```bash
cd cityeye-ai/backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Run the local API:

```bash
uvicorn app.main:app --reload
```

Verify it from another terminal:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"cityeye-ai-backend"}
```

Run Backend tests:

```bash
python -m pytest tests -q
```

Event endpoints are available in Swagger at `http://127.0.0.1:8000/docs`.
The default SQLite file is `backend/data/cityeye.db`; override it with the
`CITYEYE_DATABASE_PATH` environment variable when needed.
Evidence images are read from `ai/output/evidence` by default; override that
directory with `CITYEYE_EVIDENCE_DIR`. Evidence is available to the municipal
dashboard at `GET /evidence/{filename}` and is not automatically public on the
citizen map.
AI summary and annotated video are read from `ai/output` by default; override
that folder with `CITYEYE_AI_OUTPUT_DIR`. The Backend exposes the real last-frame
vehicle count at `GET /api/analysis/summary` and the fixed processed MP4 at
`GET /media/annotated.mp4`. `GET /api/analysis/timeline` exposes the real
per-frame vehicle and class counts used to synchronize the Dashboard with the
video playback position.

Citizen reports can be created and polled through `/api/citizen-reports`.
The Backend generates report IDs, timestamps, and the initial `PENDING` status.
When authentication is required, submission requires a valid session. Five distinct
signed-in accounts reporting the same category within 100 meters and 15 minutes
change the compatible cluster to `COMMUNITY_CONFIRMED`. The legacy `demo_user_id`
request field remains required for API compatibility but is overwritten with the
session account ID; changing it cannot create additional votes.

Existing reports receive a nullable internal `authenticated_user_id` column on
startup. Historical and demo reports are excluded from authenticated consensus;
their existing statuses are preserved, not retroactively certified. Local
no-auth demo mode still supports fixture identities and keeps its consensus
separate from authenticated reports. Production cannot disable authentication.

Create a repeatable five-report community cluster for the local competition
demo (these are clearly labeled fixtures, not AI events):

```bash
cd cityeye-ai/backend
python -m app.demo_data seed
```

Remove only the reports created by that command:

```bash
python -m app.demo_data reset
```

Both commands accept `--database /path/to/demo.db`. Running `seed` again is
safe and does not duplicate its five demo users. The reset command does not
delete real AI events or Citizen Reports submitted with other demo user IDs.

### Operational analytics semantics

The Backend stores one real live-camera observation per configured interval
(60 seconds by default) in the existing SQLite database. Query the history with
`GET /api/analytics/traffic?camera_id=camera-3&start=<unix>&end=<unix>`.

- **Average vehicles observed** is the mean active-vehicle count across stored
  samples. It is not a count of unique vehicles that passed the camera.
- **Vehicle composition** sums class observations across those sparse samples.
  A vehicle visible in more than one sample can therefore appear more than once.
- **Heavy congestion estimate** is the number of HEAVY_CONGESTION samples
  (including legacy CONGESTED) multiplied by the sampling interval. MODERATE
  is separate. This is sample-equivalent time, not measured continuous duration.
  Missing intervals, non-heavy states, and generation changes break episodes.
- **Traffic classification** includes per-state sample counts. UNKNOWN does not
  establish normal traffic. The UI reports unavailable classification if none
  of the samples has a recognized classification.
- **Chart** positions bucket averages on the actual requested time axis without
  connecting points across missing observations. No gaps are filled with zero.
- **Incidents** require source_type LIVE_CAMERA and the exact source_id in the
  selected period. Display names are never identifiers; legacy events lacking
  source metadata are excluded rather than guessed. Their stored data is unchanged.
- **Coverage** is sparse: observed_minutes is a compatibility field representing
  samples × sampling interval / 60, not a continuous uptime measurement. The UI
  flags missing recent samples when the latest observation is more than two
  sampling intervals before the requested end. It does not assert camera health.

Set `CITYEYE_ANALYTICS_SAMPLE_INTERVAL_SECONDS` to change the interval. Analytics
collection runs in the Backend, outside the live capture and AI frame hot path.

## Frontend

React + TypeScript operational UI:

```bash
cd cityeye-ai/frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173` after starting FastAPI on port `8000`; Vite proxies
`/api`, `/evidence`, and `/media`. The UI includes Command Center, Cameras,
Incidents, Analytics and role-gated account administration. Citizen Map integrates Google Maps with road/camera/incident/report layers. A restricted
Google browser key and confirmed geographic configuration are required; see
[Google Maps setup](docs/GOOGLE_MAPS_SETUP.md). Unconfigured locations are not guessed.

Recorded scenarios include `normal_traffic`, `congestion`, `stopped_vehicle`,
`rainy_traffic` and `maydan_palestine`. Generated media and analysis remain outside
Git under `ai/scenario_outputs/<scenario_id>/`. Availability depends on local assets.
`traffic_timeline.json` records processed frames alongside `tracks.csv`,
`events.json`, `annotated.mp4` and evidence. Counters follow observed timestamps;
missing analysis remains unknown. Rainy Traffic is a supplied wet-road clip, not
weather detection. See [Maydan calibration](docs/MAYDAN_PALESTINE.md) for its limits.

Live incident history uses bounded cursor pages. See [history and retention](docs/HISTORY_AND_RETENTION.md)
for the API contract, page-local filters and evidence-preservation policy, and
[stabilization validation](docs/STABILIZATION_VALIDATION.md) for tested behavior,
remaining field validations and the operator walkthrough.

Run Frontend checks:

```bash
npm test
npm run build
```

## License

University competition project — see team documentation for license details.

### Isolated validation and recovery rehearsal

Run `./scripts/smoke-test.sh` for a disposable synthetic API and database recovery check. It accepts no server URL and does not touch the running stack. See [reproducible validation](docs/REPRODUCIBLE_VALIDATION.md) for prerequisites, recorded-input preflight, clean builds and backup limitations.
