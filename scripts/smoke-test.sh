#!/bin/sh
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROJECT_NAME=${CITYEYE_SMOKE_PROJECT:-cityeye-smoke}
BACKEND_PORT=${CITYEYE_SMOKE_BACKEND_PORT:-18000}
FRONTEND_PORT=${CITYEYE_SMOKE_FRONTEND_PORT:-15173}
ADMIN_USER=smoke-admin
ADMIN_PASSWORD=CityEye-Smoke-Admin-2026!
SMOKE_TMP=$(mktemp -d "${TMPDIR:-/tmp}/cityeye-smoke.XXXXXX")

cleanup() {
  status=$?
  docker compose --project-name "$PROJECT_NAME" --project-directory "$REPO_ROOT" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -f "$SMOKE_TMP/admin_password" "$SMOKE_TMP/ingest_token"
  rmdir "$SMOKE_TMP" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT INT TERM

SCENARIO_DIR=${CITYEYE_SCENARIO_OUTPUTS_DIR:-$REPO_ROOT/ai/scenario_outputs}
AI_OUTPUT_DIR=${CITYEYE_AI_OUTPUT_DIR:-$REPO_ROOT/ai/output}
if [ ! -f "$SCENARIO_DIR/stopped_vehicle/events.json" ]; then
  echo "SMOKE TEST: FAIL" >&2
  echo "Real scenario artifacts were not found at: $SCENARIO_DIR" >&2
  echo "Set CITYEYE_SCENARIO_OUTPUTS_DIR to the directory containing the four real scenario outputs." >&2
  exit 1
fi
if [ ! -f "$AI_OUTPUT_DIR/tracks.csv" ]; then
  echo "SMOKE TEST: FAIL" >&2
  echo "Current AI artifacts were not found at: $AI_OUTPUT_DIR" >&2
  echo "Set CITYEYE_AI_OUTPUT_DIR to the directory containing tracks.csv and annotated.mp4." >&2
  exit 1
fi

printf '%s' "$ADMIN_PASSWORD" > "$SMOKE_TMP/admin_password"
printf '%s' 'cityeye-smoke-ingest-token-not-for-production' > "$SMOKE_TMP/ingest_token"
chmod 600 "$SMOKE_TMP/admin_password" "$SMOKE_TMP/ingest_token"

export CITYEYE_ENVIRONMENT=demo
export CITYEYE_AUTH_REQUIRED=true
export CITYEYE_BOOTSTRAP_ADMIN_USERNAME="$ADMIN_USER"
export CITYEYE_SECRETS_DIR="$SMOKE_TMP"
export CITYEYE_SCENARIO_OUTPUTS_DIR="$SCENARIO_DIR"
export CITYEYE_AI_OUTPUT_DIR="$AI_OUTPUT_DIR"
export CITYEYE_BACKEND_PORT="$BACKEND_PORT"
export CITYEYE_FRONTEND_PORT="$FRONTEND_PORT"

cd "$REPO_ROOT"
echo "Building the current CityEye backend and frontend images..."
docker compose --project-name "$PROJECT_NAME" build --pull backend frontend

echo "Starting an isolated CityEye smoke stack..."
docker compose --project-name "$PROJECT_NAME" up -d backend frontend

echo "Running end-to-end API and media checks..."
python3 scripts/smoke_test.py \
  --backend "http://127.0.0.1:$BACKEND_PORT" \
  --frontend "http://127.0.0.1:$FRONTEND_PORT" \
  --admin-user "$ADMIN_USER" \
  --admin-password "$ADMIN_PASSWORD"
