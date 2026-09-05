# CityEye AI — Competition MVP

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
Five distinct demo users reporting the same category within 100 meters and 15
minutes change the compatible cluster to `COMMUNITY_CONFIRMED`.

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

## Frontend (placeholder)

React + TypeScript scaffold for Days 7–9:

```bash
cd cityeye-ai/frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The first Frontend slice displays a responsive
Municipal Dashboard. Start the FastAPI Backend on port `8000` first; Vite proxies
`/api`, `/evidence`, and `/media` requests to it. The Dashboard polls real stored
events and AI output metadata every two seconds and provides working Verify and
Dismiss actions. Before video playback, live counters start at zero. During
playback, vehicle classes and events follow the corresponding timestamps from
real `tracks.csv` and `events.json` output. The Leaflet citizen map is implemented
separately.

The Dashboard offers four fixed scenarios backed only by real YOLO/ByteTrack
outputs: `normal_traffic`, `congestion`, `stopped_vehicle`, and `rainy_traffic`. Their generated
files live under `ai/scenario_outputs/<scenario_id>/` and remain outside Git.
Each folder contains `annotated.mp4`, `tracks.csv`, `events.json`, and generated
`evidence/*.jpg` files. Source clips: [normal traffic](https://www.pexels.com/video/traffic-in-an-intersecting-road-3002736/),
[congestion](https://www.pexels.com/video/cars-stuck-in-traffic-3148319/), and
[stopped vehicle](https://www.pexels.com/video/mechanic-repairing-car-on-busy-street-30125402/).
Rainy Traffic is a user-provided wet-road test clip and does not imply weather detection.
The UI resets counters to zero when switching scenarios and reveals only records
whose real video timestamps have been reached.

Run Frontend checks:

```bash
npm test
npm run build
```

## License

University competition project — see team documentation for license details.
