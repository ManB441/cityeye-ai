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

## Operations and health checks

The stack distinguishes process liveness from dependency readiness:

- `GET /health/live` confirms that the Backend process is alive.
- `GET /health/ready` verifies SQLite and reports AI artifact availability.
- Missing AI output is reported as `degraded`, not as a hard failure, because
  the camera worker is optional until a live source is configured.
- Docker waits for Backend readiness before starting Frontend and restarts
  failed services with `unless-stopped`.

Application requests are logged as one JSON object per line. Every response has
an `X-Request-ID`; send your own value to trace one request across a proxy. Docker
rotates logs to prevent them from filling the host disk.

Useful operator commands:

```bash
docker compose ps
docker compose logs --tail=100 backend
docker compose logs -f backend live-ai
curl http://127.0.0.1:8000/health/ready
```

For a clean shutdown that allows in-flight requests to finish:

```bash
docker compose down
```

## Database backups and recovery

The `database-backup` service creates a verified SQLite backup when it starts
and repeats on `CITYEYE_BACKUP_INTERVAL_SECONDS`. Backups live in the separate
`cityeye_database_backups` Docker volume. Each backup has a SHA-256 manifest,
passes `PRAGMA integrity_check`, and is published atomically. Retention is
controlled by `CITYEYE_BACKUP_RETENTION_COUNT`. Docker also marks the backup
worker unhealthy if its latest backup is missing, stale, corrupt, or has a
checksum mismatch.

Create and list backups manually:

```bash
docker compose run --rm database-backup python -m app.backups backup
docker compose run --rm database-backup python -m app.backups list
```

Restore is intentionally an operator action. Stop services that write to the
database, choose a filename from the list, restore it, and start the stack:

```bash
docker compose stop frontend backend database-backup
docker compose run --rm --no-deps database-backup \
  python -m app.backups restore cityeye-YYYYMMDDTHHMMSS.ffffffZ.sqlite3
docker compose up -d
curl --fail http://127.0.0.1:${CITYEYE_BACKEND_PORT:-8000}/health/ready
```

The restore command rejects files outside the backup volume, verifies the
manifest checksum and SQLite integrity, and replaces the database atomically.
Docker volumes protect data from container replacement, but they remain on one
host. Production must also copy encrypted backups to separate storage and test
off-host recovery regularly.

## Optional live camera worker

The live AI worker is an optional profile until a real RTSP camera URL is
available:

```bash
export CITYEYE_RTSP_URL='rtsp://username:password@camera-host:554/stream'
docker compose --profile live up --build
```

Never commit an RTSP URL containing camera credentials.
