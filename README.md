# CityEye AI — Competition MVP

Two-week MVP for a team of three developers. Proves CityEye AI can analyze real traffic video, detect and track vehicles, generate traffic events, and display results on a municipal dashboard and citizen map.

**This repository is intentionally simple** — no microservices, Redis, PostGIS, Docker, advanced auth, or custom model training.

## MVP scope

| Phase | Days | Deliverable |
|-------|------|-------------|
| **Slice 1 (current)** | 1–3 | MP4 → YOLO detect/track → `annotated.mp4` + `tracks.csv` |
| Slice 2 | 4–6 | WRONG_WAY, STOPPED_VEHICLE, CONGESTION events + evidence JPGs |
| Slice 3 | 7–9 | FastAPI + SQLite, Municipal Dashboard, Citizen Map |
| Slice 4 | 10–14 | Integration, demo data, UI polish, README rehearsal |

### Required features (full MVP)

- Video sources: local MP4, webcam, optional RTSP
- Pretrained lightweight YOLO (cars, buses, trucks, motorcycles)
- ByteTrack (or YOLO built-in tracker)
- Events: WRONG_WAY, STOPPED_VEHICLE, CONGESTION
- React app: Municipal Dashboard + Citizen Traffic Map (Leaflet/OSM)
- Python, OpenCV, FastAPI, SQLite, 2-second API polling
- Configurable thresholds in JSON; road polygon + allowed direction in config

### Out of scope for slice 1

Event detection, FastAPI backend, React UI, citizen reports, OCR, authentication.

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

### Run detection + tracking

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
| `ai/output/tracks.csv` | Per-frame detections: frame, track_id, class, bbox, confidence |

On first run, Ultralytics downloads `yolov8n.pt` (~6 MB) automatically.

## Frontend (placeholder)

React + TypeScript scaffold for Days 7–9:

```bash
cd cityeye-ai/frontend
npm install
npm run dev
```

## License

University competition project — see team documentation for license details.
