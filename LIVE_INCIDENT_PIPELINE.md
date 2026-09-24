# Live incident persistence

The backend consumes mounted Camera 3 AI artifacts at startup and every two
seconds, independently of browsers. It validates the existing event ingest schema,
waits for a complete JPG, and stores proposals in the existing `events_v2` table.
The external token-protected `/api/events/ingest` endpoint keeps its existing
contract (201 for a new ID, 409 for a duplicate). Local artifact ingestion uses the
same repository and event model, without an HTTP request back into its own server.

## Before / after

Previously the worker wrote `events.json` and JPG evidence. Live API reads merged
file proposals with any review decisions; only a review or external ingest stored
a DB row. Incidents listed recorded scenarios only.

Now the background importer persists proposals automatically. Command Center's
camera-specific events API and Incidents read the same stored UUID and decision.
Incidents combines persistent LIVE records with the existing RECORDED DEMO source
API, deduplicated by event ID. Recorded video timestamps remain video-relative;
live observations display wall-clock timestamps.

## Delivery and identity

- `event_id` is the original AI UUID and existing database primary key.
- `source_type` and `source_id` are additive nullable columns; old records and API
  payloads remain valid. Imported proposals use LIVE_CAMERA and the mounted camera
  directory ID. Timestamp, camera name, evidence reference and AI details survive.
- Successful unchanged file snapshots are skipped. Failed imports are retried;
  one invalid proposal does not prevent other valid proposals from being stored.
- Restart replay looks up UUIDs before inserting and never overwrites a decision.
  Concurrent duplicate insertion is caught by the existing unique constraint.
- Previously reviewed lazy imports can acquire source identity without resetting
  their decision or AI metadata.
- AI RTSP initialization restores pending file proposals before publishing new
  ones. JSON publication uses fsync plus atomic replacement. Corrupt existing
  files fail closed instead of being silently overwritten. Detection rules,
  thresholds, tracking, capture and model selection are unchanged.

## Evidence and review

JPGs stay in the existing mounted `ai/live_output/camera-3/evidence` directory;
SQLite contains references, not image blobs. Existing authenticated evidence
routes are reused. Import rejects traversal and escaping symlinks. Worker restart
does not delete evidence and live evidence filenames already include random IDs.

OPERATOR reads; REVIEWER/ADMIN decide through the existing protected endpoints.
Decision update and audit insert now commit in one SQLite transaction. An audit
failure rolls back the decision. All AI delivery is PROPOSED, never auto-verified.

## Limits

- Database and mounted evidence must both be backed up. Deleting the evidence
  directory still loses images; deleting operational JSON does not erase DB rows.
- JSON retention is an operational replay buffer, not the authoritative incident
  history. No pruning/acknowledgement service was added for this stabilization.
- Deduplication is per AI UUID, not semantic merging of different proposals for
  the same physical occurrence after tracker restart.
- Collection delay is normally up to two seconds; unavailable/invalid artifacts
  retry and are logged. It runs for configured live camera IDs, currently Camera 3.
- No Analytics, authentication policy, detector, tracker, event-rule, calibration,
  Citizen Map or Login design changes are part of this task.

## Validation

Automated tests cover background delivery without opening the UI, retries,
concurrent replay, preexisting decisions, source identity, evidence traversal,
Verify/Dismiss for REVIEWER and ADMIN, OPERATOR denial, backend reinitialization,
review/audit persistence, and rollback when audit insertion fails. AI tests cover
producer restart and failed atomic publication. Frontend tests cover both source
labels, live evidence, wrong-way metadata, decisions and remount persistence.

Current validation result: 222 backend tests, 188 AI tests and 45 frontend tests
passed; production builds succeeded locally and in Docker. A separate browser
instance used two controlled events emitted by the real EventPipeline against
synthetic trajectories, with real JPGs and a temporary database. Verify and
Dismiss both persisted with audit records. After an actual backend process restart
and AI producer replay, the browser still showed exactly two records, their
original decisions and working evidence; recorded fallback remained visible.

The local backend/frontend were rebuilt after a database backup. The existing
Camera 3 proposal was automatically imported as PROPOSED. Controlled test events
were never placed in the live camera directory or live database.
Camera 3 was then gracefully restarted alone to load the persistence fix. It
returned ONLINE with fresh frames and retained the original event UUID. The live
incident remained PROPOSED, and no live incident review audit was created.
