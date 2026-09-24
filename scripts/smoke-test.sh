#!/bin/sh
set -eu
REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN=${CITYEYE_SMOKE_PYTHON:-$REPO_ROOT/backend/.venv/bin/python}
if [ ! -x "$PYTHON_BIN" ]; then
  echo "Backend Python missing. Create backend/.venv and install backend/requirements.txt, or set CITYEYE_SMOKE_PYTHON." >&2
  exit 1
fi
exec "$PYTHON_BIN" "$REPO_ROOT/scripts/smoke_test.py" "$@"
