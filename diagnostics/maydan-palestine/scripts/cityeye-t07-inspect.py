import json,csv,sys,hashlib
from pathlib import Path
import cv2,numpy as np
root=Path('/Users/abcd/cityeye-ai');sys.path.insert(0,str(root/'ai'));from event_rules import point_in_polygon
out=root/'diagnostics/maydan-palestine';run=out/'calibrated-run';c=json.loads((root/'ai/config/scenarios/maydan_palestine.json').read_text());profile=c['recorded_calibration']
with (run/'tracks.csv').open() as f:rows=list(csv.DictReader(f))
frames=json.loads((run/'traffic_timeline.json').read_text())['frames'];events=json.loads((run/'events.json').read_text())
source=cv2.VideoCapture(str(root/'ai/sample_videos/maydan_palestine.mp4'));result=cv2.VideoCapture(str(run/'annotated.mp4'))
meta=lambda cap:{'width':int(cap.get(3)),'height':int(cap.get(4)),'fps':cap.get(5),'frames':int(cap.get(7))}
assert meta(source)==meta(result),(meta(source),meta(result))
assert len(frames)==6243 and all(f['frame']==i and abs(f['timestamp_sec']-i/20)<.001 for i,f in enumerate(frames))
assert {f['traffic_state'] for f in frames}=={'UNKNOWN'}
assert all(e['event_type'] not in ['WRONG_WAY','CONGESTION','ROAD_BLOCKAGE'] for e in events)
comparisons=[]
for n in [0,600,1200,2400,3600,4800,6000]:
 source.set(cv2.CAP_PROP_POS_FRAMES,n);a,raw=source.read();result.set(cv2.CAP_PROP_POS_FRAMES,n);b,annotated=result.read();assert a and b
 diff=np.abs(raw.astype(float)-annotated.astype(float));unchanged=float(np.mean(np.max(diff,axis=2)<30));comparisons.append({'frame':n,'timestamp_sec':n/20,'fraction_pixels_with_channel_difference_under_30':unchanged})
 assert unchanged>.65,'Annotated image does not sufficiently resemble source'
 cv2.polylines(annotated,[np.array(profile['monitored_road_polygon'])],True,(0,220,0),2)
 cv2.polylines(annotated,[np.array(profile['stopped_vehicle_polygon'])],True,(0,180,255),2)
 cv2.putText(annotated,'RECORDED DEMO | Direction OFF | Congestion UNKNOWN',(10,555),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),2)
 cv2.imwrite(str(out/f'yolo-roi-{n:04}.jpg'),annotated)
vehicles=[r for r in rows if r['class_name'] in c['vehicle_classes']]
inside=lambda row,poly:point_in_polygon((float(row['center_x']),float(row['center_y'])),poly)
report={'source_sha256':profile['source_sha256'],'metadata':meta(source),'timeline_frames':len(frames),'timestamp_alignment':'PASS','same_scene_comparisons':comparisons,'all_detections':len(rows),'vehicle_detections':len(vehicles),'distinct_vehicle_track_ids':len({r['track_id'] for r in vehicles if r['track_id']}),'vehicle_confidence_range':[min(float(r['confidence']) for r in vehicles),max(float(r['confidence']) for r in vehicles)],'road_roi_vehicle_observations':sum(inside(r,profile['monitored_road_polygon']) for r in vehicles),'outside_road_roi_vehicle_observations':sum(not inside(r,profile['monitored_road_polygon']) for r in vehicles),'stopped_roi_vehicle_observations':sum(inside(r,profile['stopped_vehicle_polygon']) for r in vehicles),'events':events,'traffic_states':sorted({f['traffic_state'] for f in frames}),'limitations':['Detection-row counts are repeated per-frame observations, not unique vehicle throughput.','Distinct track IDs do not certify identity continuity.','Stopped ROI is configured, not a validated positive stopped incident.','Coordinates 0,0 remain unverified location placeholders.','Artifacts are staged, not deployed to the running app.']}
(out/'validation-report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ['same_scene_comparisons','events','limitations']},indent=2))
source.release();result.release()
