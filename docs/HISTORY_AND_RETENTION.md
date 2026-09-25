# Incident history and evidence retention

## Bounded live history

`GET /api/events` returns at most 100 events by default (limit 1–200), ordered by
`timestamp DESC, event_id ASC`. `total` is the matching snapshot count, not the
page length. `next_cursor` is null at the end; otherwise send it unchanged with
the same optional `source_type` and `source_id` filters. Invalid or source-mismatched
cursors return 400; invalid limits return 422. Clients must not assume total equals
the number of returned rows.

The cursor records an insertion watermark and last timestamp/ID. Later inserts,
including backdated events, stay out of the active traversal. Timestamps and IDs
are immutable in the current event/review APIs. Review status stays current; this
is a stable membership snapshot, not a frozen copy of every event field. Start
without a cursor to see newer incidents. Cursors are selection tokens, not
credentials; existing session and role checks apply to every page. Do not reuse
cursors after a database replacement or manual deletion.

Incidents shows one page of LIVE_CAMERA records and offers Older/Latest controls.
Its status/severity filters apply to that page and the recorded demos, as stated
in the UI. It does not accumulate all pages in browser memory. Recorded demo
artifacts remain separate finite scenario files and are not cursor-paginated by
this change. The selected live-camera Command Center endpoint returns the latest
100 source-matched records; older history is available through Incidents.

Indexes support timestamp/ID order and source/time lookup. Analytics aggregates
incident type/status in SQL instead of materializing the complete event history.
Exact total counts still require scanning matching index entries; the change
bounds response and object allocation, not constant query time at arbitrary scale.

## Retention policy: preserve until explicitly approved

No automatic deletion of incidents, review/audit history, or evidence is enabled.
Pagination is not retention and does not remove old events. Dismissed incidents
continue referencing their evidence. Keep source identity and review records
when archiving. Do not delete evidence solely because its filename is old or an
incident is dismissed.

Before any future destructive retention run:

1. Produce a read-only inventory of candidate records and media, including all
   references from persisted events, legacy records, recorded scenario artifacts
   and live outputs. A missing reference in one table does not prove a file unused.
2. Verify a database backup and a coordinated copy of referenced media and
   configuration. SQLite backup alone contains no image or video files.
3. Present the exact candidates, age policy, retained references and recovery
   location for explicit operator approval. No retention period is invented here.
4. Only after approval, perform the bounded archive/deletion operation while
   preventing ingestion/review races, then verify all retained references resolve.

The existing database-backup worker has its separately configured backup-copy
retention; it is not an event/evidence retention policy. T11 does not run that
worker against production or prune any production backup.
