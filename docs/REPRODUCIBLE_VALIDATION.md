# Reproducible validation and recovery rehearsal

## Safe smoke test

From the repository root:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.runtime.txt 'pytest>=8,<9'
./scripts/smoke-test.sh
```

If the environment already exists, only run the final command. Set
`CITYEYE_SMOKE_PYTHON` to an alternate Python executable if needed.

This replaces the obsolete Docker/remote-target smoke script. It no longer
accepts `--backend`, `--frontend`, administrator credentials or a destination DB.
It does not run Docker cleanup commands. All CityEye environment variables are
isolated before application import. The application, secrets, source database,
backup and restored database live in a disposable directory removed on exit.

The smoke test uses a clearly labeled SYNTHETIC proposal. It checks authentication,
ADMIN/EMPLOYEE/CITIZEN permissions, Verify/Dismiss persistence, session revocation,
backup checksum and SQLite integrity, equality of restored schema/data, and login,
review state and audit history after restarting on the restored DB. It does not
certify actual detection, moved-then-stopped events, evidence image quality,
frontend interaction, Docker networking, or video playback. It requires no camera,
model weights, recorded videos, production secrets or network service.

## Recorded source preflight

```sh
python3 scripts/check-recorded-inputs.py --config ai/config/scenarios/maydan_palestine.json
```

Supply the approved video at `ai/sample_videos/maydan_palestine.mp4` and YOLO
weights at `ai/yolov8n.pt`, or use the local paths in your configuration. Relative
paths resolve against `ai/`; `--ai-root` permits a different asset root. The
script does not download assets or modify configuration. It checks nonempty local
files and the exact calibrated video SHA-256 where configured. Actual decoding,
model compatibility, geometry validation and positive event acceptance still
require the existing pipeline tests. Do not reuse geometry for a different video.

These binary assets are intentionally absent from Git. Missing assets produce
instructions instead of claiming a successful inference run. Native libVLC is
also required for live RTSP capture (python-vlc alone is insufficient); the AI
Dockerfile installs the native packages. FFmpeg is required when preparing
browser-compatible H.264 exports. Neither is needed for the isolated API smoke.

## Build and tests

```sh
backend/.venv/bin/python -m pytest backend/tests -q
cd frontend
npm ci
npm test -- --cache=false
npm run build
```

Use `frontend/package-lock.json` with `npm ci`. Backend and AI runtime pins are in
`backend/requirements.runtime.txt` and `ai/requirements.runtime.txt`; their
Dockerfiles use Python 3.11. The frontend Dockerfile builds with Node 20 and pins
its base image digest. The AI Dockerfile also pins torch/torchvision and installs
native VLC/OpenCV dependencies. Development requirements contain ranges and must
not be described as a fully locked environment.

T10 local validation used Python 3.13.14, Node 22.23.2 and npm 10.9.8. Backend
packages were FastAPI 0.115.14, HTTPX 0.28.1, Uvicorn 0.52.4 and pytest 8.4.2.
The existing AI environment reports Ultralytics 8.4.121, OpenCV 5.0.0.93,
python-vlc 3.0.21203, torch 2.13.0 and torchvision 0.28.0. Its NumPy 2.5.2 differs
from the runtime pin 2.4.6; T10 did not reinstall it or claim to validate AI
inference under the pinned Docker environment.

A clean source snapshot (tracked files plus the T10 changes; no local assets,
secrets, node_modules or databases) passed `npm ci --offline --no-audit --no-fund`
and `npm run build` using the existing npm cache. The clean snapshot smoke passed
using the existing backend virtual environment. This verifies source isolation,
not a fresh Python package installation or a Docker image rebuild.

## Backup rehearsal and deployment boundary

The smoke runner calls the production backup/restore helpers only with temporary
paths. It verifies the backup manifest/checksum and `PRAGMA integrity_check`,
restores into a different file, compares complete SQLite dumps, verifies the source
hash is unchanged, and starts the application against the restored copy.
The existing backup regression tests also cover tampering, path restrictions and
retention in temporary directories.

Do not run the restore CLI with its default `/data/cityeye.db` destination for a
rehearsal. A database backup does not include external evidence images, videos,
configuration or secrets; these need a coordinated operator recovery plan.
The synthetic rehearsal proves DB recovery mechanics, not recovery of a full
production deployment. No production restore or deletion is part of this task.

TLS, public exposure, rate limiting and production disaster recovery remain
separate deployment work. Do not expose the stack to perform these tests.
