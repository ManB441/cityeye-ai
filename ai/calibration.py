"""Opt-in, camera-bound spatial validation. Never rescale an unverified scene."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import hypot, isfinite

from event_rules import point_in_polygon


def _point(value, width, height):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in value) and 0 <= value[0] < width and 0 <= value[1] < height


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _intersects(a, b, c, d):
    def on(a, b, p):
        return abs(_cross(a,b,p)) < 1e-9 and min(a[0],b[0]) <= p[0] <= max(a[0],b[0]) and min(a[1],b[1]) <= p[1] <= max(a[1],b[1])
    x,y,z,t = _cross(a,b,c),_cross(a,b,d),_cross(c,d,a),_cross(c,d,b)
    return (x*y < 0 and z*t < 0) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)


def polygon_error(points, width, height):
    if not isinstance(points, list) or len(points) < 3:
        return "missing polygon (at least three points required)"
    if not all(_point(p,width,height) for p in points):
        return "polygon has invalid or out-of-frame coordinates"
    if len({tuple(p) for p in points}) != len(points):
        return "polygon has duplicate vertices"
    area2 = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points, points[1:]+points[:1]))
    if abs(area2) < 1e-9:
        return "degenerate polygon"
    n=len(points)
    for i in range(n):
        if abs(_cross(points[i-1],points[i],points[(i+1)%n])) < 1e-9:
            return "polygon has a degenerate edge/vertex"
        for j in range(i+1,n):
            if j == i+1 or (i == 0 and j == n-1): continue
            if _intersects(points[i],points[(i+1)%n],points[j],points[(j+1)%n]):
                return "self-intersecting polygon"
    return None



def _contained(points, parent):
    """Check entire edges, including edges crossing a concave parent's notch."""
    if not all(point_in_polygon(tuple(p), parent) for p in points): return False
    for a,b in zip(points,points[1:]+points[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        length2=dx*dx+dy*dy
        if length2 <= 1e-18: continue
        cuts=[0.0,1.0]
        for c,d in zip(parent,parent[1:]+parent[:1]):
            ex,ey=d[0]-c[0],d[1]-c[1]
            denom=dx*ey-dy*ex
            if abs(denom)>1e-9:
                t=((c[0]-a[0])*ey-(c[1]-a[1])*ex)/denom
                u=((c[0]-a[0])*dy-(c[1]-a[1])*dx)/denom
                if 0<=t<=1 and 0<=u<=1: cuts.append(t)
            elif abs(_cross(a,b,c))<1e-9:
                cuts.extend(t for t in [((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length2 for p in [c,d]] if 0<=t<=1)
        cuts=sorted(set(cuts))
        if any(not point_in_polygon((a[0]+dx*(lo+hi)/2,a[1]+dy*(lo+hi)/2),parent) for lo,hi in zip(cuts,cuts[1:])): return False
    return True


def direction_error(direction, width, height, polygon):
    if not isinstance(direction, dict): return "missing allowed direction"
    a,b=direction.get("start"),direction.get("end")
    if not _point(a,width,height) or not _point(b,width,height):
        return "direction has invalid or out-of-frame coordinates"
    if hypot(b[0]-a[0], b[1]-a[1]) <= 1e-9: return "zero-length direction vector"
    if not _contained([a,b], polygon):
        return "direction leaves its zone"
    return None


@dataclass
class Calibration:
    config: dict
    report: dict

    def enabled(self, rule):
        return self.report["rules"][rule]["status"] == "READY"

    @property
    def movement_scale(self):
        if not self.enabled("road"): return None
        points=self.config["monitored_road_polygon"]
        return hypot(max(p[0] for p in points)-min(p[0] for p in points), max(p[1] for p in points)-min(p[1] for p in points))


def has_camera_calibration(config):
    if str(config.get("source_type", "VIDEO_FILE")).upper() != "RTSP" or "camera_calibrations" not in config: return False
    profiles=config["camera_calibrations"]
    return not isinstance(profiles,dict) or config.get("camera_id") in profiles


def resolve_camera_calibration(config, frame_size=None):
    """Return None for legacy/recorded configs; opt-in failures disable only affected rules."""
    if not has_camera_calibration(config): return None
    profiles=config["camera_calibrations"]
    profile=profiles.get(config["camera_id"]) if isinstance(profiles,dict) else None
    effective=deepcopy(config)
    effective.update(monitored_road_polygon=[], stopped_vehicle_polygon=[], direction_zones=[], allowed_direction={}, blockage_zones=[])
    rules={}
    report={"camera_id":config["camera_id"], "frame_size":list(frame_size) if frame_size else None, "coordinate_space":"absolute_pixels", "rules":rules, "active_geometry":{}}
    def set_rule(name, error):
        rules[name]={"status":"CALIBRATION_REQUIRED" if error else "READY", "diagnostic":error}
    common=None
    if not isinstance(profile,dict): common="invalid calibration profile"
    elif profile.get("camera_id") != config["camera_id"]: common="calibration belongs to a different camera"
    elif profile.get("coordinate_space") != "absolute_pixels": common="unsupported coordinate space"
    elif frame_size is None: common="waiting for actual frame dimensions"
    elif list(frame_size) != profile.get("frame_size"): common="frame resolution mismatch; explicit recalibration required"
    if common:
        for rule in ["road","stopped_vehicle","congestion","wrong_way","person_in_road"]: set_rule(rule,common)
    else:
        width,height=frame_size
        road=profile.get("monitored_road_polygon")
        road_error=polygon_error(road,width,height)
        if not road_error and profile.get("road_confirmed") is not True: road_error="road surface not visually confirmed"
        set_rule("road",road_error);set_rule("congestion",road_error);set_rule("person_in_road",road_error)
        if not road_error:
            effective["monitored_road_polygon"]=deepcopy(road)
            report["active_geometry"]["road_and_congestion"]=deepcopy(road)
        stopped=profile.get("stopped_vehicle_polygon")
        stopped_error=road_error or polygon_error(stopped,width,height)
        if not stopped_error and not _contained(stopped, road): stopped_error="stopped ROI extends outside confirmed road"
        if not stopped_error and profile.get("stopped_confirmed") is not True: stopped_error="stopped zone not visually confirmed"
        set_rule("stopped_vehicle",stopped_error)
        if not stopped_error:
            effective["stopped_vehicle_polygon"]=deepcopy(stopped)
            report["active_geometry"]["stopped_vehicle"]=deepcopy(stopped)
        zones=profile.get("direction_zones")
        direction_problem=road_error
        if not direction_problem and (not isinstance(zones,list) or not zones): direction_problem="missing direction zones"
        if not direction_problem:
            for zone in zones:
                if not isinstance(zone,dict): direction_problem="invalid direction zone";break
                p=zone.get("polygon")
                direction_problem=polygon_error(p,width,height)
                if not direction_problem and not _contained(p,road): direction_problem="direction zone outside confirmed road"
                if not direction_problem: direction_problem=direction_error(zone.get("allowed_direction"),width,height,p)
                if direction_problem: break
        if not direction_problem and profile.get("direction_confirmed") is not True: direction_problem="permitted direction has no verified camera-specific evidence"
        set_rule("wrong_way",direction_problem)
        if not direction_problem:
            effective["direction_zones"]=deepcopy(zones)
            report["active_geometry"]["direction_zones"]=deepcopy(zones)
    rules["road_blockage"]={"status":"CONFIGURATION_REQUIRED", "diagnostic":"No approved blockage zone, movement direction or upstream-impact calibration; remains disabled."}
    report["status"]="READY" if all(rules[r]["status"] == "READY" for r in ["road","stopped_vehicle","congestion","wrong_way"]) else "CALIBRATION_REQUIRED"
    report["note"]=profile.get("note", "") if isinstance(profile,dict) else ""
    return Calibration(effective,report)
