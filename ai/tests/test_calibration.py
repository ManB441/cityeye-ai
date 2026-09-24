"""Calibration boundaries are independent of detection/event algorithms."""
from copy import deepcopy
from pathlib import Path
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibration import polygon_error, direction_error, resolve_camera_calibration
from event_pipeline import EventPipeline
from process_video import build_live_metrics_snapshot
from trajectory import TrajectoryManager, VehicleMovementState


def config():
    return {
        'camera_id':'camera-3', 'camera_name':'Controlled calibration test',
        'source_type':'RTSP', 'latitude':31.9, 'longitude':35.9,
        'event_thresholds':{'stopped_vehicle_seconds':8},
        # Deliberately unusable generic geometry must not leak into this camera.
        'monitored_road_polygon':[[100,100],[1180,100],[1180,650],[100,650]],
        'camera_calibrations':{'camera-3':{
            'camera_id':'camera-3','coordinate_space':'absolute_pixels','frame_size':[944,1080],
            'road_confirmed':True,'stopped_confirmed':True,'direction_confirmed':True,
            'monitored_road_polygon':[[100,100],[800,100],[800,900],[100,900]],
            'stopped_vehicle_polygon':[[200,200],[700,200],[700,800],[200,800]],
            'direction_zones':[{'name':'controlled','polygon':[[200,200],[700,200],[700,800],[200,800]],'allowed_direction':{'start':[300,500],'end':[600,500]}}],
        }},
    }


def test_valid_camera_geometry_has_only_in_frame_points_and_no_input_mutation():
    c=config();before=deepcopy(c);v=resolve_camera_calibration(c,(944,1080))
    assert c==before and v.report['status']=='READY'
    assert v.enabled('road') and v.enabled('stopped_vehicle') and v.enabled('wrong_way')
    for name in ['monitored_road_polygon','stopped_vehicle_polygon']:
        assert polygon_error(v.config[name],944,1080) is None
        assert all(0<=x<944 and 0<=y<1080 for x,y in v.config[name])
    assert v.config['monitored_road_polygon']!=c['monitored_road_polygon']
    assert v.config['event_thresholds']==c['event_thresholds']


@pytest.mark.parametrize('polygon',[
    [],[[1,1],[2,2]],[[1,1],[2,2],[3,3]],
    [[1,1],[944,1],[20,20]], [[1,1],[2,1080],[20,20]],
    [[-1,1],[2,2],[20,20]], [[float('nan'),1],[2,2],[20,20]],
    [[1,1],[2,float('inf')],[20,20]],
    [[1,1],[20,1],[20,20],[1,1]],
    [[1,1],[30,25],[1,30],[20,1]],
])
def test_invalid_polygon_is_rejected(polygon):
    assert polygon_error(polygon,944,1080)


@pytest.mark.parametrize('direction',[
    {},{'start':[1,1],'end':[1,1]},
    {'start':[1,1],'end':[1080,500]},
    {'start':[1,1],'end':[float('nan'),500]},
    {'start':[1,1],'end':[15,15]},
])
def test_invalid_direction_is_rejected(direction):
    assert direction_error(direction,944,1080,[[10,10],[20,10],[20,20],[10,20]])


@pytest.mark.parametrize('mutation,size,diagnostic',[
    ({'camera_id':'camera-7'},(944,1080),'different camera'),
    ({},(944,1090),'resolution mismatch'),
    ({},None,'waiting for actual'),
    ({'coordinate_space':'normalized'},(944,1080),'unsupported'),
])
def test_wrong_camera_or_resolution_fails_closed(mutation,size,diagnostic,tmp_path):
    c=config();c['camera_calibrations']['camera-3'].update(mutation)
    pipeline=EventPipeline(c,tmp_path,frame_size=size)
    assert not pipeline.wrong_way_rules and pipeline.stopped_vehicle_rule is None and pipeline.congestion_rule is None
    assert diagnostic in pipeline.calibration.report['rules']['road']['diagnostic']
    assert pipeline.evaluate_frame(1,[],np.zeros((30,30,3),dtype=np.uint8))==[]


def test_bad_stopped_geometry_disables_only_stopped_rule(tmp_path):
    c=config();c['camera_calibrations']['camera-3']['stopped_vehicle_polygon']=[[0,0],[1180,0],[100,100]]
    p=EventPipeline(c,tmp_path,(944,1080))
    assert p.stopped_vehicle_rule is None and p.congestion_rule is not None and len(p.wrong_way_rules)==1
    assert p.evaluate_frame(1,[],np.zeros((30,30,3),dtype=np.uint8))==[]


def test_unverified_or_zero_direction_never_invents_legal_movement(tmp_path):
    for i,change in enumerate([{'direction_confirmed':False},{'direction_zones':[{'polygon':[[100,100],[200,100],[200,200],[100,200]],'allowed_direction':{'start':[150,150],'end':[150,150]}}]}]):
        c=config();c['camera_calibrations']['camera-3'].update(change)
        p=EventPipeline(c,tmp_path/str(i),(944,1080))
        assert not p.wrong_way_rules and p.congestion_rule is not None and p.stopped_vehicle_rule is not None


def test_actual_camera3_daylight_geometry_keeps_unproven_direction_disabled(tmp_path):
    c=json.loads((Path(__file__).resolve().parents[1]/'config/live_camera.json').read_text());c['camera_id']='camera-3'
    p=EventPipeline(c,tmp_path,(944,1080))
    assert p.calibration.report['status']=='CALIBRATION_REQUIRED'
    assert p.calibration.enabled('road') and p.calibration.enabled('stopped_vehicle')
    assert p.calibration.enabled('congestion')
    assert p.road_blockage_rule is None
    assert p.stopped_vehicle_rule is not None and p.congestion_rule is not None
    assert c['camera_calibrations']['camera-3']['source_condition']=='DAYLIGHT_ONLY'
    from event_rules import point_in_polygon, VehicleObservation
    road=p.calibration.config['monitored_road_polygon']
    assert polygon_error(road,944,1080) is None
    assert point_in_polygon((450,350),road)
    outside=[(345,50),(34,373),(720,167),(700,300),(850,550)]
    assert all(not point_in_polygon(pt,road) for pt in outside)
    observations=[VehicleObservation(x,y,x-10,y-10,x+10,y+10,.9,i) for i,(x,y) in enumerate([(450,350)]+outside)]
    assert p.congestion_rule.calculate_metrics(1,observations).vehicles_in_roi==1
    assert not p.wrong_way_rules
    assert p.evaluate_frame(1,[],np.zeros((30,30,3),dtype=np.uint8))==[]


def test_recorded_config_is_unchanged_even_if_live_profile_present():
    c=config();c['source_type']='VIDEO_FILE';before=deepcopy(c)
    assert resolve_camera_calibration(c,(1920,1080)) is None and c==before
    for path in (Path(__file__).resolve().parents[1]/'config/scenarios').glob('*.json'):
        recorded=json.loads(path.read_text());before=deepcopy(recorded)
        assert resolve_camera_calibration(recorded,(640,480)) is None and recorded==before


def test_unknown_geometry_does_not_publish_road_normalized_movement():
    states={1:SimpleNamespace(movement_state=VehicleMovementState.MOVING),2:SimpleNamespace(movement_state=VehicleMovementState.STATIONARY)}
    payload=build_live_metrics_snapshot(frame_idx=1,timestamp=100,generation=1,frame_rows=[{'class_name':'car','track_id':1},{'class_name':'car','track_id':2}],traffic_state='UNKNOWN',current_track_states=states,movement_calibrated=False)
    assert payload['active_vehicle_count']==2 and payload['active_track_count']==2
    assert payload['moving_vehicles']==payload['stationary_vehicles']==0
    assert payload['unknown_movement_vehicles']==2 and payload['traffic_state']=='UNKNOWN'


def test_worker_revalidates_dimensions_and_resets_tracks_on_reconnect(tmp_path,monkeypatch):
    import process_video as worker
    from frame_source import CameraHealth, CameraState, FramePacket, SourceType
    c=config();c['debug_traffic_analysis']=True
    packets=iter([
        FramePacket(np.zeros((1080,944,3),dtype=np.uint8),1,100,1),
        FramePacket(np.zeros((1080,944,3),dtype=np.uint8),2,101,1),
        FramePacket(np.zeros((1090,944,3),dtype=np.uint8),3,102,1),
        FramePacket(np.zeros((1080,944,3),dtype=np.uint8),4,103,2),
    ])
    class Source:
        def __init__(self,**kw):
            self.health=CameraHealth(camera_id='camera-3',source_type=SourceType.RTSP,state=CameraState.ONLINE)
        def read(self,timeout):return next(packets)
        def close(self):pass
    class Model:
        def __init__(self,*args):pass
        def track(self,*args,**kw):
            box=SimpleNamespace(cls=np.array(2),conf=np.array(.9),id=np.array(7),xyxy=np.array([[300,300,400,400]]))
            person=SimpleNamespace(cls=np.array(0),conf=np.array(.9),id=np.array(8),xyxy=np.array([[10,10,30,50]]))
            bicycle=SimpleNamespace(cls=np.array(1),conf=np.array(.9),id=np.array(9),xyxy=np.array([[300,300,340,360]]))
            return [SimpleNamespace(boxes=[box,person,bicycle])]
    managers=[]
    class Manager(TrajectoryManager):
        def __init__(self,**kw):super().__init__(**kw);managers.append(self)
    writes=[];real_write=worker.write_json_atomic
    def write(path,data):
        writes.append((path.name,deepcopy(data)));return real_write(path,data)
    monkeypatch.setattr(worker,'RTSPFrameSource',Source)
    monkeypatch.setattr(worker,'YOLO',Model)
    monkeypatch.setattr(worker,'TrajectoryManager',Manager)
    monkeypatch.setattr(worker,'resolve_rtsp_url',lambda _: 'rtsp://controlled.invalid/test')
    monkeypatch.setattr(worker,'write_json_atomic',write)
    worker.process_video(None,c,tmp_path,max_frames=4)
    reports=[d for n,d in writes if n=='calibration_status.json']
    assert [d['status'] for d in reports]==['READY','CALIBRATION_REQUIRED','READY']
    assert [d['generation'] for d in reports]==[1,1,2]
    snapshots=[d for n,d in writes if n=='live_metrics.json' and d['current_detection_count']==3]
    assert len(snapshots)==4
    assert snapshots[2]['traffic_state']=='UNKNOWN' and snapshots[2]['unknown_movement_vehicles']==1
    assert all(d['bicycles'] == 1 for d in snapshots)
    assert snapshots[-1]['generation']==2
    assert len(managers)==4  # Initial, first calibrated frame, shape change, generation change.
    assert len(managers[-1].tracks[7].history)==1
    assert json.loads((tmp_path/'events.json').read_text())==[]


def test_polygon_and_vector_cannot_cross_a_concave_road_notch(tmp_path):
    c=config();p=c['camera_calibrations']['camera-3']
    p['monitored_road_polygon']=[[100,100],[800,100],[800,900],[600,900],[600,300],[300,300],[300,900],[100,900]]
    # All child vertices are inside the road; its top edge crosses the excluded notch.
    p['stopped_vehicle_polygon']=[[200,400],[700,400],[700,800]]
    result=resolve_camera_calibration(c,(944,1080))
    assert result.enabled('road') and not result.enabled('stopped_vehicle')
    assert direction_error({'start':[200,400],'end':[700,400]},944,1080,p['monitored_road_polygon'])


@pytest.mark.parametrize('profiles',[None,[],{'camera-3':None}])
def test_malformed_calibration_fails_closed_without_crashing_worker(profiles,tmp_path):
    c=config();c['camera_calibrations']=profiles
    p=EventPipeline(c,tmp_path,(944,1080))
    assert p.calibration.report['status']=='CALIBRATION_REQUIRED'
    assert p.congestion_rule is None and p.stopped_vehicle_rule is None and not p.wrong_way_rules


@pytest.mark.parametrize("camera_id", ["camera-5", "camera-7"])
def test_missing_live_profile_never_uses_generic_geometry(camera_id, tmp_path):
    c = config()
    c["camera_id"] = camera_id
    c["allowed_direction"] = {"start": [200, 500], "end": [800, 500]}
    before = deepcopy(c)
    pipeline = EventPipeline(c, tmp_path, frame_size=(944, 1080))
    assert pipeline.calibration is not None
    assert not pipeline.calibration.enabled("road")
    assert pipeline.congestion_rule is None
    assert pipeline.stopped_vehicle_rule is None
    assert not pipeline.wrong_way_rules
    assert c == before
