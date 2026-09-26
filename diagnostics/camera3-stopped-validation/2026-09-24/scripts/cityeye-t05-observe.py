import json,time,hashlib,shutil,datetime
from pathlib import Path
root=Path('/Users/abcd/cityeye-ai'); src=root/'ai/live_output/camera-3'; out=root/'diagnostics/camera3-stopped-validation/2026-09-24'
start=time.monotonic(); start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(); samples=[]
for name in ['events.json','calibration_status.json']:
 shutil.copy2(src/name,out/('before-'+name))
while True:
 row={'observed_at':time.time()}
 for name in ['camera_status','live_metrics']:
  try: row[name]=json.loads((src/(name+'.json')).read_text());row[name+'_file_age']=time.time()-(src/(name+'.json')).stat().st_mtime
  except Exception as exc: row[name]={'read_error':type(exc).__name__}
 try:
  data=(src/'preview.jpg').read_bytes();row['preview_sha256']=hashlib.sha256(data).hexdigest()
  if len(samples)%30==0: (out/f'live-{len(samples):03}.jpg').write_bytes(data)
 except Exception as exc: row['preview_error']=type(exc).__name__
 samples.append(row)
 with (out/'live-observation.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 if time.monotonic()-start>=300:break
 time.sleep(2)
for name in ['events.json','calibration_status.json']:
 shutil.copy2(src/name,out/('after-'+name))
shutil.copy2(src/'preview.jpg',out/'validation-frame.jpg')
(out/'observation-summary.json').write_text(json.dumps({'start_utc':start_utc,'duration_seconds':time.monotonic()-start,'samples':len(samples),'distinct_preview_hashes':len({s.get('preview_sha256') for s in samples}),'frames':len({s['live_metrics'].get('frame') for s in samples}),'max_vehicles':max(s['live_metrics'].get('active_vehicle_count',0) for s in samples),'max_tracks':max(s['live_metrics'].get('active_track_count',0) for s in samples)},indent=2))
print('Observation complete',flush=True)
