# CityEye AI Docker Operations

Docker Compose starts the production-built Frontend and FastAPI Backend, keeps
the SQLite database in a persistent volume, and mounts existing AI results as
read-only inputs.

## Start the dashboard

```bash
docker compose up --build
```

This uses the stable demo defaults. For an explicit demo environment:

```bash
docker compose --env-file config/environments/demo.env.example up --build
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

## Development environment

The development override mounts source code and enables Backend and Frontend
hot reload:

```bash
docker compose \
  --env-file config/environments/development.env.example \
  -f compose.yaml -f compose.dev.yaml up --build
```

The normal `compose.yaml` uses production-built assets and contains no source
code mounts. Copy an example environment file to a local `.env` when values
need customization; `.env` is excluded from Git.

## Production environment

Use the production template as a starting point and inject secrets through the
deployment platform rather than writing them to the file:

```bash
docker compose --env-file config/environments/production.env.example up -d --build
```

Runtime Python dependencies and base-image digests are pinned so rebuilding the
same commit does not silently upgrade FastAPI, Ultralytics, PyTorch, Node, or
Nginx. Test-only dependencies remain in the developer requirements files.

## Optional live camera worker

The live AI worker is an optional profile until a real RTSP camera URL is
available:

```bash
export CITYEYE_RTSP_URL='rtsp://username:password@camera-host:554/stream'
docker compose --profile live up --build
```

Never commit an RTSP URL containing camera credentials.
