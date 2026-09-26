# P0 #3.7 — Stopped Vehicle validation

**Real Camera 3: NOT VALIDATED. Recorded scenario: FAIL as a positive acceptance test.** The existing clip contains an already-stationary broken car. A false proposal caused by brief bounding-box motion was found and fixed. It is not evidence of a real moved-then-stopped episode.

## CAMERA 3 REAL VALIDATION
- moving observed: **YES**
- stopped transition observed: **NO**
- ROI valid: **YES**
- event generated: **NO**
- evidence generated: **NO**
- DB persisted: **NO**

Observed 300.0 seconds (2026-09-18T12:09:41.078368+00:00 to 2026-09-18T12:14:41.125809+00:00), 835 diagnostic AI frames, 167 production snapshots and 24 diagnostic tracks. No new STOPPED_VEHICLE UUID, evidence path, DB record or incident status exists.

Production evidence: [track46](live/production-620.jpg), [track54](live/production-635.jpg). Independent diagnostic tracks52/58 were MOVING inside the stopped ROI at centers(417,289)/(451.5,288), stationary duration0.0s. All observed inside-ROI stationary durations were0.0s. See [per-track transitions](live-track-summary.json) and [full state samples](live/states.jsonl).

Read-only live preview observer running unchanged production YOLO/ByteTrack and process_video configuration in a separate process, alongside passive production outputs and event monitoring. No diagnostic event was imported as Camera 3.

- Observer IDs 52 and 58 are NOT production IDs 46 and 54. Independent timing/JPEG input means internal production movement state cannot be inferred exactly from observer state.
- Production per-track stationary timers are not exposed by current runtime; the numerical timers in states.jsonl are diagnostic observations, not worker telemetry.
- Five-minute observation began before the stopped-rule fix; worker was restarted after successful tests and returned ONLINE. No post-fix positive real episode is claimed.
- Snapshot images are reference/validation artifacts, not generated incident evidence.

Existing calibration is unchanged: 944×1080, stopped polygon `[[385, 260], [570, 255], [520, 400], [380, 610], [170, 610], [235, 440]]`. Live stop duration8s; release0.025 ROI diagonals/s; stationary0.01 ROI diagonals/s; rearm1s; prior motion required. Daylight-only manual night-disable requirement remains.

## RECORDED SCENARIO VALIDATION
- Valid event generated after fix: **NO**
- Valid event evidence after fix: **NO**
- Valid new positive event DB persistence after fix: **NO**
- Duplicate suppression: **PASS**

Re-ran all318 frames through current model/tracker/config without threshold changes. This clip uses1.5s stopped duration, not Camera3’s8s. Before fix, track7 was STATIONARY initially, briefly classified MOVING at2.0667s, then STATIONARY at2.5667s. A single proposal was emitted at4.0s. The car was visibly already broken down; box motion is not proof it drove. After fix, the same clip emits **zero events**. Thus this is a useful negative regression, not a successful positive stopped-event scenario.

## Minimal bug fix
TrackState.has_moved becomes sticky after brief high-speed bbox jitter. StoppedVehicleRule accepted that boolean alone as prior motion. Recorded track7 exceeded release threshold0.18 for only0.0333 seconds at2.0667–2.1000, yet emitted at4.0 seconds.

StoppedVehicleRule now qualifies initial prior motion using sustained movement above the existing release threshold for the existing rearm_moving_seconds. Counts motion before entering ROI; clears qualification after observation gaps. Global trajectory states, all other event rules, thresholds, YOLO and ByteTrack unchanged.

Brief genuine motion shorter than the existing rearm interval will not qualify a first stopped episode. Sustained detector/box errors can still require further diagnosis; this does not prove perfect physical motion recognition.

220 AI tests passed, plus23 stopped tests after strengthening rearm coverage;69 backend tests passed. Positive event generation, no-repeat behavior and rearm are **synthetic regression checks only**, never passed off as Camera3 evidence. Camera3 worker was restarted with the tested rule and is ONLINE.

## Evidence, DB and human review
Historical pre-fix proposal `35b9c58c-3051-4d46-a049-0aa1a916dd94` was explicitly labelled **RECORDED DEMO — bbox-jitter regression** and ingested as `RECORDED_SCENARIO/stopped_vehicle`. This deliberately tests handling/rejecting a false AI proposal, not correctness of a stop. Ingest201, duplicate409, evidence200. It was PROPOSED in DB before review, visible in Command Center at4.0s, then **DISMISSED** from the evidence dialog and remained DISMISSED in Incidents and DB.

See [DB before review](db-ingest.json), [DB after review/audit](db-after.json), [Command Center](command-center-proposed.png), [evidence dialog](evidence-review.png), and [Incidents after review](incidents-dismissed.png). Actual UI account was the existing ADMIN. The same recorded proposal was tested with REVIEWER credentials in isolated temporary DBs for both Verify and Dismiss, evidence access, persistence and duplicate delivery; see [reviewer regression](recorded-review-regression.json). No existing live incident was verified/dismissed by this task.

Replaced the stopped demo events.json with this explicitly labelled historical pre-fix proposal and copied matching generated evidence, so it is reviewable in the existing UI. Its DB status is DISMISSED. Prior demo event/evidence files are backed up locally. No new Camera 3 incident was created, and unrelated existing incidents were not reviewed.

## Changes and limitations
Production change is confined to StoppedVehicleRule eligibility. Tests were updated/added. YOLO, ByteTrack, camera pipeline, live/recorded configuration, detection thresholds, road/stopped polygons and authentication remain byte-identical to baseline; see hash checks in JSON. No commit/push. No production instrumentation remains.

## Final acceptance status
STOPPED VEHICLE:
- REAL CAMERA = NOT VALIDATED
- RECORDED SCENARIO = FAIL

PIPELINE:
- Detection = PASS — Actual production and recorded vehicle boxes observed. Not exhaustive recall validation.
- Tracking = PASS — Production IDs 46/54 and recorded ID7; observer IDs explicitly separate.
- State transition = FAIL — FAIL means the required genuine physical moved-then-stopped sequence was not proven; state-machine synthetic regressions pass.
- Event = FAIL — FAIL means no valid new positive stopped proposal after fix in tested footage; event writing works in controlled regression.
- Evidence = PASS — PASS for actual generated pre-fix recorded proposal image, HTTP200 and UI View; no real-camera incident evidence.
- DB persistence = PASS — PASS for labelled pre-fix RECORDED_SCENARIO proposal, not a valid Camera 3 stop.
- Review workflow = PASS — Actual UI View and Dismiss by existing ADMIN; Verify and Dismiss by REVIEWER in isolated test DBs with the same recorded proposal.
- Duplicate suppression = PASS — Actual replay emitted one pre-fix proposal rather than every frame; post-fix emits zero false proposals. Automated positive stopped-episode and movement/rearm tests emit exactly one per episode. Duplicate DB ingest returns409 and preserves review status.

## Single next action
Obtain one naturally occurring Camera 3 daylight sequence showing sustained movement, entry/presence in the existing stopped ROI, then at least8 seconds stopped, and rerun positive end-to-end acceptance.
