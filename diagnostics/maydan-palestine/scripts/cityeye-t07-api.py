import sys,json,tempfile,os
from pathlib import Path
root=Path('/Users/abcd/cityeye-ai');sys.path[:0]=[str(root/'backend')]
from fastapi.testclient import TestClient
from app.main import create_app
out=root/'diagnostics/maydan-palestine';run=out/'calibrated-run'
with tempfile.TemporaryDirectory(prefix='cityeye-t07-api-') as td:
 tmp=Path(td);scenario=tmp/'scenarios/maydan_palestine';scenario.mkdir(parents=True)
 for name in ['tracks.csv','traffic_timeline.json','events.json']:
  os.link(run/name,scenario/name)
 os.link(out/'annotated-browser.mp4',scenario/'annotated.mp4')
 os.environ['CITYEYE_AUTH_REQUIRED']='false'
 with TestClient(create_app(database_path=tmp/'test.db',scenario_output_root=tmp/'scenarios',live_output_dir=tmp/'live',ai_output_dir=tmp/'ai',evidence_dir=tmp/'evidence')) as client:
  timeline=client.get('/api/scenarios/maydan_palestine/analysis/timeline');assert timeline.status_code==200
  data=timeline.json();assert data['status']=='READY' and len(data['frames'])==6243
  assert {f['traffic_state'] for f in data['frames']}=={'UNKNOWN'}
  assert all(f['duration_sec']==.05 for f in data['frames'])
  response=client.get('/media/scenarios/maydan_palestine/annotated.mp4',headers={'Range':'bytes=0-4095'})
  assert response.status_code==206 and len(response.content)==4096
  expected=(out/'annotated-browser.mp4').open('rb').read(4096);assert response.content==expected
  events=client.get('/api/scenarios/maydan_palestine/events');assert events.status_code==200
  summary=client.get('/api/scenarios/maydan_palestine/analysis/summary');assert summary.status_code==200
  report={'isolated_backend':True,'auth_scope':'local no-auth test mode only; production auth untouched','timeline_http':timeline.status_code,'frames':len(data['frames']),'range_playback_http':response.status_code,'range_bytes':len(response.content),'events':events.json()['total'],'summary':summary.json()}
 (out/'api-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
