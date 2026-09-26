from pathlib import Path
import json,hashlib,cv2,numpy as np
root=Path('/Users/abcd/cityeye-ai');out=root/'diagnostics/camera3-stopped-validation/2026-09-24'
observation=json.loads((out/'observation-summary.json').read_text());recorded=json.loads((out/'recorded-summary.json').read_text());synthetic=json.loads((out/'synthetic/summary.json').read_text());db=json.loads((out/'production-stopped-db.json').read_text())
before=json.loads((out/'before-events.json').read_text());after=json.loads((out/'after-events.json').read_text());new=[e for e in after if e['event_id'] not in {e['event_id'] for e in before}]
c=json.loads((root/'ai/config/live_camera.json').read_text());profile=c['camera_calibrations']['camera-3']
image=cv2.imread(str(out/'validation-frame.jpg'));cv2.polylines(image,[np.array(profile['stopped_vehicle_polygon'])],True,(0,180,255),3)
for i,line in enumerate(['CAMERA 3 - CURRENT OBSERVATION','944 x 1080 | DAYLIGHT CALIBRATION ONLY','Configured stopped ROI shown, NOT visually validated','NO OBSERVED MOVING -> STOPPED EPISODE','Not incident evidence; no incident generated']):
 cv2.putText(image,line,(15,40+i*32),cv2.FONT_HERSHEY_SIMPLEX,.56,(0,220,255),2)
cv2.imwrite(str(out/'validation-overlay.jpg'),image)
report={'task':'T05 Stopped Vehicle end-to-end','status':'PARTIAL - positive real/recorded validation not established','camera3_real_validation':{'moving_observed':'NO','stopped_transition_observed':'NO','roi_valid':'NO - geometry is configured but daylight-only ROI cannot be visually confirmed in current dark/glared frames','event_generated':'NO','evidence_generated':'NO','db_persisted':'NO','track_ids':[],'movement_state_transitions':[],'stationary_duration':None,'event_uuid':None,'evidence_path':None,'db_record':None,'incident_status':None,'telemetry_limit':'Production output exposes aggregate counts, not per-track states/timers. No IDs or durations were invented.',**observation,'new_events':new,'production_stopped_db_records':db},'recorded_scenario_validation':{'label':'RECORDED DEMO','event_generated':'NO','evidence':'NO','db_persistence':'NO','duplicate_suppression':'NOT VALIDATED for positive recorded episode','positive_acceptance':'FAIL','configured_stationary_seconds':1.5,'source':recorded,'reason':'No qualifying moved-then-stopped event. Prominent vehicle already has hood/trunk open at clip start. Current source resolution is 1920x1080; generic scenario ROI has no declared reference resolution, so spatial relevance is not newly certified.'},'synthetic_validation':{**synthetic,'not_real_camera_or_recorded_demo':True,'backend_results':json.loads((out/'synthetic/backend-validation.json').read_text()),'scope':'Actual event/trajectory/evidence/import/review code driven by synthetic coordinates and images; bypasses detection and ByteTrack.'},'tests':{'ai_stopped_and_pipeline':38,'backend_live_import':11,'frontend':77,'typescript':'PASS'},'production_changes':'NONE; no source, thresholds, geometry, authentication, events or database changes. No worker restart. Only frontend regression tests added.','next_action':'Capture a clear daytime Camera 3 sequence showing sustained vehicle movement inside the existing ROI, followed by at least 8 seconds stopped; rerun positive end-to-end acceptance.','artifact_hashes':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'ai/config/live_camera.json',root/'ai/config/scenarios/stopped_vehicle.json',root/'ai/event_rules.py',root/'ai/process_video.py']}}
(out/'validation-report.json').write_text(json.dumps(report,indent=2))
md=f'''# T05 — Stopped Vehicle validation, 2026-09-24

**PARTIAL: real-camera positive validation is NOT VALIDATED; recorded positive acceptance FAILS. Controlled synthetic pipeline checks PASS. These are separate results.**

## Camera 3 real validation

Observed {observation['duration_seconds']:.1f} seconds beginning {observation['start_utc']}; {observation['samples']} samples, {observation['frames']} distinct sampled AI frame numbers, {observation['distinct_preview_hashes']} distinct preview hashes. Maximum observed vehicles/tracks: {observation['max_vehicles']}/{observation['max_tracks']}.

Moving observed: NO. Stopped transition: NO. ROI valid for current image: NO (configured daytime polygon is geometrically present; current dark/glared image does not support visual validation). New event/evidence/DB record: NO. No UUID or incident status exists for a new stopped episode. Production DB read-only query returned {len(db)} STOPPED_VEHICLE records. Before/after event artifacts contain {len(new)} new events.

No production per-track timer is exposed. With zero sampled tracks, there are no track IDs, ROI memberships or stationary durations to report; these are unavailable, not numerical zero-duration evidence. Snapshot/overlay are validation images, not event evidence. The overlay displays existing coordinates only and does not approve them for nighttime use. The existing 8-second threshold and manual nighttime-disable requirement remain unchanged.

## Recorded scenario validation — RECORDED DEMO

Reran the current model/configuration against all {int(recorded['frames'])} frames ({int(recorded['width'])}×{int(recorded['height'])}, {recorded['fps']} FPS). {recorded['track_records']} detection/track rows, {len(recorded['track_ids'])} distinct assigned IDs; zero events. Assigned IDs establish tracking execution, not robust long-term identity: substantial ID churn remains a limitation.

Event generated: NO. Evidence: NO. DB persistence of new recorded proposal: NO. Positive duplicate suppression: NOT VALIDATED. Clip threshold is 1.5 seconds, not Camera 3's 8 seconds. The prominent vehicle is already stopped with hood/trunk open in the first reference image. Zero events is not proof of a successful positive stop, and may be appropriate for pre-existing stationary vehicles. The generic scenario ROI has no declared reference resolution; no new spatial calibration claim is made.

## Synthetic regression — explicitly NOT Camera 3 or recorded-demo validation

Used current Camera 3 thresholds and calibrated geometry, with artificial trajectories and a clearly labeled synthetic image. Actual EventPipeline produced exactly two STOPPED_VEHICLE proposals: one per episode at 10.4s and 26.4s after motion/rearm, each with 8 seconds stationary. A separate vehicle stationary from the beginning produced none. Continued stationary observations produced no duplicate incidents.

Generated UUIDs: {', '.join(synthetic['event_ids'])}. See `synthetic/events.json`, `synthetic/states.json`, and generated JPG evidence. These artifacts never entered the production database.

Four isolated backend cases (EMPLOYEE/ADMIN × Verify/Dismiss) automatically imported the generated events, served exact evidence bytes, exposed incident list/detail endpoints, preserved decisions through replay and backend restart, and retained exactly two records. Temporary databases were removed. UI tests separately verified stopped details, View, Verify/Dismiss and remount persistence using controlled API responses; this was not a manual browser-to-production-DB exercise.

## Checks and changes

38 stopped/pipeline AI tests, 11 backend importer tests, and all 77 frontend tests passed; TypeScript passed. No production behavior changed. Two stopped-review frontend regressions were added. Diagnostic scripts ran outside the worker; no production instrumentation was installed. The existing historical September 18 report remains untouched in the parent directory.

## Acceptance status

STOPPED VEHICLE:
REAL CAMERA = NOT VALIDATED
RECORDED SCENARIO = FAIL

PIPELINE:
Detection = PASS (recorded detections only)
Tracking = PASS (recorded assigned IDs; continuity not certified)
State transition = FAIL (no observed qualifying natural transition; synthetic regression passes)
Event = FAIL (no qualifying real/recorded positive event; synthetic generation passes)
Evidence = PASS (synthetic pipeline only)
DB persistence = PASS (isolated synthetic import only)
Review workflow = PASS (isolated API and frontend regression only)
Duplicate suppression = PASS (synthetic episode/rearm and import replay only)

## Single next action

Capture a clear daytime Camera 3 sequence showing sustained movement inside the existing ROI, followed by at least 8 seconds stopped, then rerun positive acceptance. Do not mark the feature end-to-end validated before that evidence exists.
'''
(out/'validation-report.md').write_text(md)
print(json.dumps(observation))
