# Stabilization validation and operator walkthrough

This is a source/test checkpoint, not a production deployment certification.
Each task has its detailed evidence in FEATURE_STABILIZATION_PLAN.md. Local camera
images, recordings, diagnostics, DBs and credentials are excluded from Git.

## Current feature evidence

- Incident review (T01/T04): PASS automated success/failure, Verify/Dismiss,
  stale polling, source switching, history refresh, focus/Escape and evidence error
  checks. Failed requests never become successful reviews locally.
- Recorded counters (T02): PASS processed zero observations, missing-data gaps,
  seeking and source changes. Counts represent observations, not unique throughput.
- Calibration safety (T03): PASS invalid bounds/identity/resolution and disabled-rule
  regression. This does not establish road geometry from an unseen camera.
- Stopped Vehicle (T05): PARTIAL / real Camera 3 NOT VALIDATED. Synthetic state,
  rearm, duplicate suppression, import/evidence/review checks passed. The existing
  recorded clip did not provide a qualifying positive event. User deferred natural
  positive validation; no synthetic event is represented as camera evidence.
- Live reliability (T06): PARTIAL. Controlled stale/retry/generation tests passed;
  short passive observations did not demonstrate natural reconnect recovery time.
  Camera 3 calibration remains daylight-only with manual nighttime disable.
- Maydan Palestine (T07): PARTIAL / staged. Full recorded analysis and conservative
  source-bound ROI checks passed; no positive stopped event occurred. Wrong Way and
  Congestion remain disabled, geographic coordinates unverified, and some model
  recall/classification limitations observed. Outputs were not deployed.
- Roles/report consensus (T08): PASS isolated direct API checks and trusted-account
  consensus. CITIZEN remains limited to the citizen surface; its map provider is
  not configured. Historical report statuses are not retroactively certified.
- Analytics (T09): PASS source identity, sparse real timestamps, zero/unknown,
  moderate/heavy separation and failure-path regressions. Estimates are sampled
  observations, not measured throughput, speed or continuous duration.
- Reproducibility/recovery (T10): PASS isolated synthetic smoke and disposable DB
  backup/restore. Clean-source frontend build passed. Full production disaster
  recovery, fresh Python dependency installation and Docker rebuild were not run.
- History (T11): PASS bounded cursor pages and SQL incident aggregation over 5,006
  synthetic events, including equal timestamps and a backdated concurrent insert.
  Reference-preservation checks passed; no event/evidence deletion was performed.

## Operator walkthrough after deployment

The automated suites cover these flows in fixtures. The following is an operator
checklist for the deployed build, not a claim that production was redeployed or
that a manual browser run already completed:

1. Sign in as each provisioned role. ADMIN can manage users; EMPLOYEE can operate
   and review but not administer accounts; CITIZEN cannot open operational pages
   or their protected API routes. Log out and confirm the session cannot be reused.
2. Open Command Center live mode. Confirm source identity and freshness; stale or
   unavailable measurements must not appear live. Do not interrupt the sole camera
   merely to simulate a reconnect during a demo.
3. Open each available recorded source, seek across positive/zero/missing analysis
   and switch sources. Video/time/labels must match; missing data stays unknown.
   Run the recorded-input preflight before generating new outputs.
4. On an isolated test deployment, View a proposed fixture and Verify/Dismiss it.
   Confirm persisted state after reload, evidence error fallback, and visible retry
   on API failure. Do not modify real operational incidents for a smoke test.
5. Open Incidents with a seeded disposable history. Traverse Older pages, verify
   no duplicate IDs, and return to Latest for new arrivals. Filters are page-local.
6. Open Analytics. Check correct camera ID, timestamp spacing, unknown periods,
   sample labels, and distinct moderate/heavy counts. Absence of observations must
   not be interpreted as zero traffic.
7. Run `./scripts/smoke-test.sh` for isolated recovery rehearsal. Never restore a
   test backup over the live DB. Follow HISTORY_AND_RETENTION.md before any deletion.

## Final regression checkpoint

Final suites passed: 269 backend tests, 231 AI tests and 85 frontend tests. TypeScript, Vite production build, isolated synthetic recovery smoke and diff checks passed.
No model, tracking, event thresholds, camera calibration or production data are
changed by T11. Remaining field validations above remain open even when all
software tests pass.
