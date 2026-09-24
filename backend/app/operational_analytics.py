"""Collection and truthful aggregation of sparse live-camera observations."""

from __future__ import annotations

from collections import Counter
import logging
import math
from pathlib import Path

from app.database import EventRepository, TrafficObservationRepository
from app.live_camera import read_live_snapshot
from app.schemas import (
    AnalyticsSeriesPoint,
    OperationalAnalyticsResponse,
    TrafficObservation,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_SAMPLE_INTERVAL_SECONDS = 60
CONGESTED_STATES = {"HEAVY_CONGESTION", "CONGESTED"}


def collect_live_observation(
    *,
    camera_id: str,
    directory: Path,
    repository: TrafficObservationRepository,
    interval_seconds: int = DEFAULT_SAMPLE_INTERVAL_SECONDS,
) -> bool:
    """Store one current sample per interval; invalid/offline state is skipped."""
    try:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        snapshot = read_live_snapshot(directory, camera_id)
        health, metrics = snapshot.health, snapshot.metrics
        if metrics is None:
            return False
        interval_start = math.floor(metrics.timestamp / interval_seconds) * interval_seconds
        observation = TrafficObservation(
            camera_id=camera_id,
            interval_start=interval_start,
            observed_at=metrics.timestamp,
            generation=metrics.generation,
            vehicles=metrics.active_vehicle_count,
            cars=metrics.cars,
            buses=metrics.buses,
            trucks=metrics.trucks,
            motorcycles=metrics.motorcycles,
            bicycles=metrics.bicycles,
            people=metrics.people,
            moving_vehicles=metrics.moving_vehicles,
            stationary_vehicles=metrics.stationary_vehicles,
            traffic_status=metrics.traffic_state,
            capture_fps=health.camera_capture_fps,
            ai_fps=health.ai_inference_fps or health.processing_fps,
        )
        return repository.add(observation)
    except Exception:
        # Analytics must never take down live capture or the API process.
        LOGGER.exception("Could not persist analytics sample for %s", camera_id)
        return False


def choose_bucket_seconds(start: float, end: float) -> int:
    duration = max(0.0, end - start)
    if duration <= 6 * 3600:
        return 5 * 60
    if duration <= 2 * 24 * 3600:
        return 15 * 60
    return 60 * 60


def _bucket_observations(
    observations: list[TrafficObservation], bucket_seconds: int
) -> list[AnalyticsSeriesPoint]:
    buckets: dict[float, list[TrafficObservation]] = {}
    for observation in observations:
        bucket = math.floor(observation.observed_at / bucket_seconds) * bucket_seconds
        buckets.setdefault(bucket, []).append(observation)
    series = []
    for timestamp, items in sorted(buckets.items()):
        states = Counter(item.traffic_status for item in items)
        series.append(AnalyticsSeriesPoint(
            timestamp=timestamp,
            average_vehicles_observed=round(
                sum(item.vehicles for item in items) / len(items), 2
            ),
            peak_vehicles_observed=max(item.vehicles for item in items),
            samples=len(items),
            traffic_status=states.most_common(1)[0][0],
        ))
    return series


def _congestion_summary(
    observations: list[TrafficObservation], interval_seconds: int
) -> tuple[int, float]:
    episodes = 0
    congested_samples = 0
    previous: TrafficObservation | None = None
    for observation in observations:
        if observation.traffic_status not in CONGESTED_STATES:
            previous = None
            continue
        congested_samples += 1
        if (
            previous is None
            or observation.generation != previous.generation
            or observation.interval_start - previous.interval_start > interval_seconds * 1.5
        ):
            episodes += 1
        previous = observation
    return episodes, round(congested_samples * interval_seconds / 60, 1)


def build_operational_analytics(
    *,
    camera_id: str,
    start: float,
    end: float,
    observations: list[TrafficObservation],
    data_since: float | None,
    events,
    interval_seconds: int = DEFAULT_SAMPLE_INTERVAL_SECONDS,
) -> OperationalAnalyticsResponse:
    bucket_seconds = choose_bucket_seconds(start, end)
    series = _bucket_observations(observations, bucket_seconds)
    peak = max(series, key=lambda point: point.average_vehicles_observed, default=None)
    episodes, congestion_minutes = _congestion_summary(
        observations, interval_seconds
    )
    period_events = [
        event for event in events
        if event.source_type == "LIVE_CAMERA" and event.source_id == camera_id
        and start <= event.timestamp <= end
    ]
    by_type = Counter(event.event_type.value for event in period_events)
    by_status = Counter(event.status.value for event in period_events)
    composition = {
        key: sum(getattr(item, key) for item in observations)
        for key in ("cars", "buses", "trucks", "motorcycles", "bicycles")
    }
    samples = len(observations)
    return OperationalAnalyticsResponse(
        camera_id=camera_id,
        requested_start=start,
        requested_end=end,
        data_since=data_since,
        first_sample_at=observations[0].observed_at if observations else None,
        latest_sample_at=observations[-1].observed_at if observations else None,
        sampling_interval_seconds=interval_seconds,
        bucket_seconds=bucket_seconds,
        samples=samples,
        average_vehicles_observed=(
            round(sum(item.vehicles for item in observations) / samples, 2)
            if samples else None
        ),
        peak_vehicle_count=(peak.average_vehicles_observed if peak else None),
        peak_period_start=(peak.timestamp if peak else None),
        peak_period_end=(peak.timestamp + bucket_seconds if peak else None),
        congestion_episodes=episodes,
        congestion_duration_minutes=congestion_minutes,
        incident_count=len(period_events),
        average_capture_fps=(
            round(sum(item.capture_fps for item in observations) / samples, 2)
            if samples else None
        ),
        average_ai_fps=(
            round(sum(item.ai_fps for item in observations) / samples, 2)
            if samples else None
        ),
        observed_minutes=round(samples * interval_seconds / 60, 1),
        vehicle_composition_observations=composition,
        incidents_by_type=dict(sorted(by_type.items())),
        incidents_by_status=dict(sorted(by_status.items())),
        traffic_series=series,
        traffic_status_samples=dict(sorted(Counter(item.traffic_status for item in observations).items())),
    )


def query_operational_analytics(
    *,
    camera_id: str,
    start: float,
    end: float,
    observations: TrafficObservationRepository,
    events: EventRepository,
    interval_seconds: int = DEFAULT_SAMPLE_INTERVAL_SECONDS,
) -> OperationalAnalyticsResponse:
    rows = observations.list_range(camera_id, start, end)
    result = build_operational_analytics(
        camera_id=camera_id,
        start=start,
        end=end,
        observations=rows,
        data_since=observations.first_timestamp(camera_id),
        events=[],
        interval_seconds=interval_seconds,
    )
    by_type: Counter = Counter()
    by_status: Counter = Counter()
    for row in events.counts_for_source(camera_id, start, end):
        by_type[row["event_type"]] += row["count"]
        by_status[row["status"]] += row["count"]
    return result.model_copy(update={"incident_count": sum(by_type.values()),
                                     "incidents_by_type": dict(sorted(by_type.items())),
                                     "incidents_by_status": dict(sorted(by_status.items()))})
