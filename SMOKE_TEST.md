# CityEye end-to-end smoke test

Run this before every demo or deployment from the repository root:

```bash
./scripts/smoke-test.sh
```

The command rebuilds the current Backend and Frontend images, starts them as an
isolated `cityeye-smoke` Compose project, exercises the real HTTP APIs and media
artifacts, and removes only its temporary containers, database volume, users,
decisions, and credentials when finished.

The four precomputed scenario output directories are intentionally ignored by
Git. They must exist under `ai/scenario_outputs`. When they live elsewhere:

```bash
CITYEYE_SCENARIO_OUTPUTS_DIR=/absolute/path/to/scenario_outputs ./scripts/smoke-test.sh
```

The current AI output is also required for an operational readiness result. If
it is stored elsewhere, set `CITYEYE_AI_OUTPUT_DIR` to the directory containing
`tracks.csv` and `annotated.mp4`.

Optional port overrides are `CITYEYE_SMOKE_BACKEND_PORT` (default `18000`) and
`CITYEYE_SMOKE_FRONTEND_PORT` (default `15173`). A failed check exits non-zero
and identifies the endpoint or assertion that failed.
