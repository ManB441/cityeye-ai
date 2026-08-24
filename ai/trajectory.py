"""Reusable per-vehicle trajectory state for CityEye AI."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import hypot


@dataclass(frozen=True)
class TrackObservation:
    """One tracked vehicle center point at a specific video time."""

    frame: int
    timestamp_sec: float
    center_x: float
    center_y: float


@dataclass
class TrackState:
    """Bounded history and movement metrics for one ByteTrack ID."""

    track_id: int
    history_size: int
    history: deque[TrackObservation] = field(init=False)
    pixel_speed: float | None = None
    stationary_duration: float = 0.0

    def __post_init__(self) -> None:
        if self.track_id < 0:
            raise ValueError("track_id must be non-negative")
        if self.history_size < 2:
            raise ValueError("history_size must be at least 2")
        self.history = deque(maxlen=self.history_size)

    def update(
        self,
        observation: TrackObservation,
        stationary_speed_threshold: float,
        max_observation_gap_sec: float,
    ) -> None:
        """Add one observation and update speed and stationary time."""
        if stationary_speed_threshold < 0:
            raise ValueError("stationary_speed_threshold must be non-negative")
        if max_observation_gap_sec <= 0:
            raise ValueError("max_observation_gap_sec must be positive")

        if not self.history:
            self.history.append(observation)
            return

        previous = self.history[-1]
        elapsed = observation.timestamp_sec - previous.timestamp_sec
        if elapsed <= 0:
            raise ValueError("observation timestamps must increase")

        if elapsed > max_observation_gap_sec:
            self.pixel_speed = None
            self.stationary_duration = 0.0
        else:
            displacement = hypot(
                observation.center_x - previous.center_x,
                observation.center_y - previous.center_y,
            )
            self.pixel_speed = displacement / elapsed
            if self.pixel_speed <= stationary_speed_threshold:
                self.stationary_duration += elapsed
            else:
                self.stationary_duration = 0.0

        self.history.append(observation)


class TrajectoryManager:
    """Own independent trajectory state for every assigned track ID."""

    def __init__(
        self,
        history_size: int = 30,
        stationary_speed_threshold: float = 3.0,
        max_observation_gap_sec: float = 1.0,
    ) -> None:
        if history_size < 2:
            raise ValueError("history_size must be at least 2")
        if stationary_speed_threshold < 0:
            raise ValueError("stationary_speed_threshold must be non-negative")
        if max_observation_gap_sec <= 0:
            raise ValueError("max_observation_gap_sec must be positive")

        self.history_size = history_size
        self.stationary_speed_threshold = stationary_speed_threshold
        self.max_observation_gap_sec = max_observation_gap_sec
        self.tracks: dict[int, TrackState] = {}

    def update(
        self,
        track_id: int,
        frame: int,
        timestamp_sec: float,
        center_x: float,
        center_y: float,
    ) -> TrackState:
        """Update one track and return its current state."""
        state = self.tracks.get(track_id)
        if state is None:
            state = TrackState(track_id=track_id, history_size=self.history_size)
            self.tracks[track_id] = state

        state.update(
            TrackObservation(
                frame=frame,
                timestamp_sec=timestamp_sec,
                center_x=center_x,
                center_y=center_y,
            ),
            stationary_speed_threshold=self.stationary_speed_threshold,
            max_observation_gap_sec=self.max_observation_gap_sec,
        )
        return state
