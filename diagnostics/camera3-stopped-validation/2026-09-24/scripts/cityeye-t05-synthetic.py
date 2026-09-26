import sys,json
from pathlib import Path
import cv2,numpy as np
root=Path('/Users/abcd/cityeye-ai');sys.path.insert(0,str(root/'ai'))
from event_pipeline import EventPipeline
from trajectory import TrajectoryManager
out=root/'diagnostics/camera3-stopped-validation/2026-09-24/synthetic'
out.mkdir(exist_ok=True)
c=json.loads((root/'ai/config/live_camera.json').read_text());c['camera_id']='camera-3';c['camera_name']='SYNTHETIC REGRESSION - NOT CAMERA OBSERVATION'
p=EventPipeline(c,out,frame_size=(944,1080));t=c['event_thresholds']
m=TrajectoryManager(history_size=c['trajectory_history_size'],stationary_speed_threshold=t['stopped_vehicle_max_speed_px_per_sec'],max_observation_gap_sec=c['trajectory_max_observation_gap_seconds'],movement_scale=p.calibration.movement_scale,stationary_normalized_speed_threshold=t['stopped_vehicle_max_normalized_speed_per_sec'],speed_smoothing_window=t['stopped_vehicle_speed_smoothing_window'],movement_state_confirmations=c['vehicle_state_confirmations'],moving_hysteresis_multiplier=c['vehicle_state_moving_hysteresis_multiplier'])
rows=[]
for i in range(181):
 ts=i*.2
 x=400+50*ts if ts<2 else 500 if ts<16 else 500-50*(ts-16) if ts<18 else 400
 track=m.update(1,i,ts,x,350);parked=m.update(2,i,ts,440,360)
 frame=np.full((1080,944,3),25,dtype=np.uint8)
 cv2.putText(frame,'SYNTHETIC TEST - NOT REAL CAMERA',(20,40),cv2.FONT_HERSHEY_SIMPLEX,.75,(255,255,255),2)
 cv2.rectangle(frame,(int(x)-15,335),(int(x)+15,365),(0,255,255),2)
 events=p.evaluate_frame(ts,[track,parked],frame,track_classes={1:'car',2:'car'})
 rows.append({'timestamp':ts,'track_id':1,'state':track.movement_state.value,'stationary_seconds':track.stationary_duration,'events':[e.event_id for e in events]})
p.write_events_json()
assert len(p.events)==2,[(e.event_type,e.timestamp) for e in p.events]
assert all(e.event_type.value=='STOPPED_VEHICLE' and e.details['track_id']==1 for e in p.events)
assert all((out/e.evidence_image).is_file() for e in p.events)
(out/'states.json').write_text(json.dumps(rows,indent=2))
(out/'summary.json').write_text(json.dumps({'validation_type':'SYNTHETIC ONLY','stationary_threshold':t['stopped_vehicle_seconds'],'episodes':2,'events':len(p.events),'preexisting_stationary_events':0,'rearm':'PASS','duplicate_suppression':'PASS','event_ids':[e.event_id for e in p.events]},indent=2))
print('Synthetic episodes passed:',[(e.event_id,e.timestamp) for e in p.events])
