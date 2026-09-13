# CityEye AI Docker Operations

Docker Compose starts the production-built Frontend and FastAPI Backend, keeps
the SQLite database in a persistent volume, and mounts existing AI results as
read-only inputs.

## Start the dashboard

```bash
docker compose up --build
```

Open the Dashboard at `http://127.0.0.1:5173/dashboard` and the API docs at
`http://127.0.0.1:8000/docs`.

Stop the stack without deleting its database:

```bash
docker compose down
```

## Avoid port conflicts

Override either published port without changing application code:

```bash
CITYEYE_FRONTEND_PORT=5180 CITYEYE_BACKEND_PORT=8010 docker compose up
```

## Optional live camera worker

The live AI worker is an optional profile until a real RTSP camera URL is
available:

```bash
export CITYEYE_RTSP_URL='rtsp://username:password@camera-host:554/stream'
docker compose --profile live up --build
```

Never commit an RTSP URL containing camera credentials.
