import json,sys,tempfile,shutil,time
from pathlib import Path
root=Path('/Users/abcd/cityeye-ai');sys.path[:0]=[str(root/'backend'),str(root/'backend/tests')]
from fastapi.testclient import TestClient
import pytest
from app.main import create_app
from app.auth import AuthRepository
from app.database import EventRepository
from app.live_incidents import LiveIncidentImporter
from test_auth_api import configure_required_auth,login,ADMIN_PASSWORD
out=root/'diagnostics/camera3-stopped-validation/2026-09-24';source=out/'synthetic';records=[]
for role in ['EMPLOYEE','ADMIN']:
 for decision in ['verify','dismiss']:
  with tempfile.TemporaryDirectory(prefix='cityeye-t05-db-') as td, pytest.MonkeyPatch.context() as mp:
   tmp=Path(td);configure_required_auth(mp,tmp)
   live=tmp/'live';shutil.copytree(source,live/'camera-3');db=tmp/'test.db'
   kwargs=dict(database_path=db,live_output_dir=live,evidence_dir=tmp/'evidence',ai_output_dir=tmp/'ai',scenario_output_root=tmp/'scenarios')
   with TestClient(create_app(**kwargs)) as client:
    repo=EventRepository(db);deadline=time.monotonic()+5
    while len(repo.list())!=2 and time.monotonic()<deadline:time.sleep(.05)
    assert len(repo.list())==2
    if role=='EMPLOYEE':AuthRepository(db).create_user('test-employee','only-for-isolated-test-123','EMPLOYEE');login(client,'test-employee','only-for-isolated-test-123')
    else:login(client,'admin',ADMIN_PASSWORD)
    payload=json.loads((source/'events.json').read_text())[0];eid=payload['event_id'];evidence=payload['evidence_image'].split('/')[-1]
    assert repo.get(eid).status.value=='PROPOSED'
    assert client.get('/api/live-cameras/camera-3/events').json()['total']==2
    assert client.get('/api/events').json()['total']==2
    assert client.get('/evidence/live-cameras/camera-3/'+evidence).content==(source/payload['evidence_image']).read_bytes()
    result=client.post(f'/api/events/{eid}/{decision}');expected='VERIFIED' if decision=='verify' else 'DISMISSED'
    assert result.status_code==200 and result.json()['status']==expected
    LiveIncidentImporter(live,repo).sync('camera-3')
    assert len(repo.list())==2 and repo.get(eid).status.value==expected
   with TestClient(create_app(**kwargs)) as client:
    login(client,'admin',ADMIN_PASSWORD)
    assert client.get(f'/api/events/{eid}').json()['status']==expected
   records.append({'validation_type':'SYNTHETIC ONLY','role':role,'decision':decision,'event_uuid':eid,'event_generated_by':'actual EventPipeline using synthetic tracks','evidence_http':200,'db_persisted':True,'status_after_restart':expected,'duplicate_import_preserves_count_and_review':True,'database':'temporary isolated database removed after test'})
(out/'synthetic/backend-validation.json').write_text(json.dumps(records,indent=2))
print('PASS: four role/decision cases with real generated evidence, automatic import and restart persistence')
