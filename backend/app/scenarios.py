"""Safe access to the precomputed real-AI demonstration scenarios."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from app.schemas import ScenarioInfo, TrafficEventResponse


SCENARIOS = {
    "normal_traffic": ScenarioInfo(
        scenario_id="normal_traffic", title="Normal Traffic",
        description="Free-flowing intersection traffic with no event threshold reached.",
        expected_event=None,
        source_url="user-provided",
    ),
    "congestion": ScenarioInfo(
        scenario_id="congestion", title="Heavy Congestion",
        description="Dense traffic clip for evaluating congestion-threshold behavior.",
        expected_event="CONGESTION",
        source_url="user-provided",
    ),
    "stopped_vehicle": ScenarioInfo(
        scenario_id="stopped_vehicle", title="Stopped Vehicle",
        description="A disabled car remains stationary while surrounding traffic continues moving.",
        expected_event="STOPPED_VEHICLE",
        source_url="https://www.pexels.com/video/mechanic-repairing-car-on-busy-street-30125402/",
    ),
    "rainy_traffic": ScenarioInfo(
        scenario_id="rainy_traffic", title="Rainy Traffic",
        description="Traffic monitoring under rainy and wet-road conditions.",
        expected_event=None,
        source_url="user-provided",
    ),
}


def scenario_directory(root: Path, scenario_id: str) -> Path | None:
    if scenario_id not in SCENARIOS:
        return None
    candidate = (root.resolve() / scenario_id).resolve()
    return candidate if candidate.parent == root.resolve() else None


def read_scenario_events(directory: Path) -> list[TrafficEventResponse]:
    path = directory / "events.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TypeAdapter(list[TrafficEventResponse]).validate_python(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("Scenario events.json is invalid") from exc
