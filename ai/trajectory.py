"""Reusable per-vehicle trajectory state for CityEye AI."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from math import hypot
from statistics import median


class VehicleMovementState(str, Enum):
    """Smoothed behavioral state for a tracked road vehicle."""

    UNKNOWN = "UNKNOWN"
    MOVING = "MOVING"
    STATIONARY = "STATIONARY"


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
    normalized_speed: float | None = None
    smoothed_normalized_speed: float | None = None
    stationary_duration: float = 0.0
    speed_smoothing_window: int = 5
    normalized_speed_history: deque[float] = field(init=False)
    movement_state: VehicleMovementState = VehicleMovementState.UNKNOWN
    has_moved: bool = False
    moving_evidence: int = 0
    stationary_evidence: int = 0

    def __post_init__(self) -> None:
        if self.track_id < 0:
            raise ValueError("track_id must be non-negative")
        if self.history_size < 2:
            raise ValueError("history_size must be at least 2")
        if self.speed_smoothing_window < 1:
            raise ValueError("speed_smoothing_window must be positive")
        self.history = deque(maxlen=self.history_size)
        self.normalized_speed_history = deque(maxlen=self.speed_smoothing_window)

    def update(
        self,
        observation: TrackObservation,
        stationary_speed_threshold: float,
        max_observation_gap_sec: float,
        movement_scale: float = 1.0,
        stationary_normalized_speed_threshold: float | None = None,
        movement_state_confirmations: int = 2,
        moving_hysteresis_multiplier: float = 2.0,
    ) -> None:
        """Add one observation and update speed and stationary time."""
        if stationary_speed_threshold < 0:
            raise ValueError("stationary_speed_threshold must be non-negative")
        if max_observation_gap_sec <= 0:
            raise ValueError("max_observation_gap_sec must be positive")
        if movement_scale <= 0:
            raise ValueError("movement_scale must be positive")
        if (
            stationary_normalized_speed_threshold is not None
            and stationary_normalized_speed_threshold < 0
        ):
            raise ValueError("stationary_normalized_speed_threshold must be non-negative")
        if movement_state_confirmations < 1:
            raise ValueError("movement_state_confirmations must be positive")
        if moving_hysteresis_multiplier <= 1.0:
            raise ValueError("moving_hysteresis_multiplier must be greater than 1")

        if not self.history:
            self.history.append(observation)
            return

        previous = self.history[-1]
        elapsed = observation.timestamp_sec - previous.timestamp_sec
        if elapsed <= 0:
            raise ValueError("observation timestamps must increase")

        if elapsed > max_observation_gap_sec:
            self.pixel_speed = None
            self.normalized_speed = None
            self.smoothed_normalized_speed = None
            self.normalized_speed_history.clear()
            self.stationary_duration = 0.0
        else:
            displacement = hypot(
                observation.center_x - previous.center_x,
                observation.center_y - previous.center_y,
            )
            self.pixel_speed = displacement / elapsed
            self.normalized_speed = self.pixel_speed / movement_scale
            self.normalized_speed_history.append(self.normalized_speed)
            self.smoothed_normalized_speed = median(self.normalized_speed_history)
            stationary = (
                self.smoothed_normalized_speed <= stationary_normalized_speed_threshold
                if stationary_normalized_speed_threshold is not None
                else self.pixel_speed <= stationary_speed_threshold
            )
            if stationary:
                self.stationary_duration += elapsed
            else:
                self.stationary_duration = 0.0

            state_speed = (
                self.smoothed_normalized_speed
                if stationary_normalized_speed_threshold is not None
                else self.pixel_speed
            )
            stationary_limit = (
                stationary_normalized_speed_threshold
                if stationary_normalized_speed_threshold is not None
                else stationary_speed_threshold
            )
            if state_speed is not None and state_speed <= stationary_limit:
                self.stationary_evidence += 1
                self.moving_evidence = 0
                if self.stationary_evidence >= movement_state_confirmations:
                    self.movement_state = VehicleMovementState.STATIONARY
            elif (
                state_speed is not None
                and state_speed > stationary_limit * moving_hysteresis_multiplier
            ):
                self.moving_evidence += 1
                self.stationary_evidence = 0
                if self.moving_evidence >= movement_state_confirmations:
                    self.movement_state = VehicleMovementState.MOVING
                    self.has_moved = True

        self.history.append(observation)


class TrajectoryManager:
    """Own independent trajectory state for every assigned track ID."""

    def __init__(
        self,
        history_size: int = 30,
        stationary_speed_threshold: float = 3.0,
        max_observation_gap_sec: float = 1.0,
        movement_scale: float = 1.0,
        stationary_normalized_speed_threshold: float | None = None,
        speed_smoothing_window: int = 5,
        movement_state_confirmations: int = 2,
        moving_hysteresis_multiplier: float = 2.0,
    ) -> None:
        if history_size < 2:
            raise ValueError("history_size must be at least 2")
        if stationary_speed_threshold < 0:
            raise ValueError("stationary_speed_threshold must be non-negative")
        if max_observation_gap_sec <= 0:
            raise ValueError("max_observation_gap_sec must be positive")
        if movement_scale <= 0:
            raise ValueError("movement_scale must be positive")
        if stationary_normalized_speed_threshold is not None and stationary_normalized_speed_threshold < 0:
            raise ValueError("stationary_normalized_speed_threshold must be non-negative")
        if speed_smoothing_window < 1:
            raise ValueError("speed_smoothing_window must be positive")
        if movement_state_confirmations < 1:
            raise ValueError("movement_state_confirmations must be positive")
        if moving_hysteresis_multiplier <= 1.0:
            raise ValueError("moving_hysteresis_multiplier must be greater than 1")

        self.history_size = history_size
        self.stationary_speed_threshold = stationary_speed_threshold
        self.max_observation_gap_sec = max_observation_gap_sec
        self.movement_scale = movement_scale
        self.stationary_normalized_speed_threshold = stationary_normalized_speed_threshold
        self.speed_smoothing_window = speed_smoothing_window
        self.movement_state_confirmations = movement_state_confirmations
        self.moving_hysteresis_multiplier = moving_hysteresis_multiplier
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
            state = TrackState(
                track_id=track_id,
                history_size=self.history_size,
                speed_smoothing_window=self.speed_smoothing_window,
            )
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
            movement_scale=self.movement_scale,
            stationary_normalized_speed_threshold=self.stationary_normalized_speed_threshold,
            movement_state_confirmations=self.movement_state_confirmations,
            moving_hysteresis_multiplier=self.moving_hysteresis_multiplier,
        )
        return state

    def expire_stale(self, current_timestamp: float, max_age_seconds: float) -> list[int]:
        """Remove tracks not observed recently and return their IDs."""
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        expired = [
            track_id
            for track_id, state in self.tracks.items()
            if state.history
            and current_timestamp - state.history[-1].timestamp_sec > max_age_seconds
        ]
        for track_id in expired:
            del self.tracks[track_id]
        return expired
