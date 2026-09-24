#!/usr/bin/env python3
"""Read-only local calibration overlay. No RTSP access, inference or config writes."""
from pathlib import Path
import argparse
import json
import sys
import time

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ai'))
from calibration import resolve_camera_calibration


def render(frame,report):
    h,w=frame.shape[:2];margin=28;top=115;side=620
    image=np.full((h+top+70,w+margin*2+side,3),24,dtype=np.uint8)
    image[top:top+h,margin:margin+w]=frame
    def text(value,x,y,color=(230,230,230),scale=.56):
        cv2.putText(image,value,(x,y),cv2.FONT_HERSHEY_SIMPLEX,scale,color,1,cv2.LINE_AA)
    text('CAMERA 3 / SPATIAL CALIBRATION',margin,35,scale=.8)
    text(f'Actual image: {w} x {h} | pixel bounds: x=0..{w-1}, y=0..{h-1}',margin,70)
    text('Image pixels are not transformed. Geometry comes only from validated configuration.',margin,95,scale=.48)
    cv2.rectangle(image,(margin,top),(margin+w-1,top+h-1),(240,240,240),2)
    text('(0, 0)',margin+8,top+25)
    text(f'({w-1}, {h-1})',margin+w-140,top+h-12)
    x=w+margin*2;y=top+24
    color=(70,185,245)
    text(report['status'],x,y,color,.72);y+=45
    for name,item in report['rules'].items():
        text(name.replace('_',' ').upper(),x,y);y+=24
        text(item['status'],x,y,color,.5);y+=36
    active=report['active_geometry']
    def polygon(name,points,color):
        pts=np.array([[p[0]+margin,p[1]+top] for p in points],np.int32)
        cv2.polylines(image,[pts],True,color,2)
        for i,(px,py) in enumerate(points):
            cv2.circle(image,(int(px)+margin,int(py)+top),4,color,-1)
            text(f'{i}:({px:g},{py:g})',int(px)+margin+5,int(py)+top-8,color,.4)
        nonlocal y
        text(name,x,y,color,.5);y+=26
    if 'road_and_congestion' in active: polygon('ROAD = CONGESTION = PERSON-IN-ROAD',active['road_and_congestion'],(230,210,40))
    if 'stopped_vehicle' in active: polygon('STOPPED VEHICLE',active['stopped_vehicle'],(50,170,245))
    for zone in active.get('direction_zones',[]):
        polygon('WRONG WAY: '+str(zone.get('name','')),zone['polygon'],(220,90,220))
        d=zone['allowed_direction'];a=tuple(int(v) for v in np.array(d['start'])+[margin,top]);b=tuple(int(v) for v in np.array(d['end'])+[margin,top]);cv2.arrowedLine(image,a,b,(220,90,220),2,tipLength=.1)
    if not active:
        for line in ['NO ACTIVE SPATIAL GEOMETRY','Road boundaries cannot be identified','from the current obscured/defocused view.','No road polygon or legal direction is guessed.','Legacy x=1180 is outside this image.','Detections and tracking can continue.','Traffic condition remains UNKNOWN.']:
            text(line,x,y,color if line.startswith('NO ACTIVE') else (220,220,220),.49);y+=27
    text('Local diagnostic only. Road Blockage remains disabled. No real-world event validation claimed.',margin,h+top+44,scale=.52)
    return image


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'ai/config/live_camera.json')
    parser.add_argument('--source-dir',type=Path,default=ROOT/'ai/live_output/camera-3')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'diagnostics/camera3-calibration')
    args=parser.parse_args()
    health=json.loads((args.source_dir/'camera_status.json').read_text())
    data=(args.source_dir/'preview.jpg').read_bytes();mtime=(args.source_dir/'preview.jpg').stat().st_mtime
    now=time.time()
    if health.get('camera_id')!='camera-3' or health.get('state')!='ONLINE' or not 0 <= now-health.get('heartbeat_at',0)<5 or not 0<=now-mtime<5:
        raise SystemExit('Camera 3 raw preview is not currently fresh; no diagnostic produced.')
    frame=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    if frame is None: raise SystemExit('Raw preview could not be decoded.')
    config=json.loads(args.config.read_text());config['camera_id']='camera-3'
    calibration=resolve_camera_calibration(config,(frame.shape[1],frame.shape[0]))
    if calibration is None: raise SystemExit('Camera 3 has no explicit calibration profile.')
    report={**calibration.report,'captured_at':now,'preview_age_seconds':now-mtime,'generation':health.get('generation'),'orientation':'portrait' if frame.shape[0]>frame.shape[1] else 'landscape','aspect_ratio':frame.shape[1]/frame.shape[0]}
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'current-frame.jpg').write_bytes(data)
    if not cv2.imwrite(str(args.output_dir/'final-overlay.jpg'),render(frame,report)): raise SystemExit('Cannot save diagnostic image.')
    (args.output_dir/'calibration-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'overlay':str(args.output_dir/'final-overlay.jpg'),'frame_size':report['frame_size'],'status':report['status']}))
if __name__=='__main__':main()
