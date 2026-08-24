from pathlib import Path
import sys

import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from trajectory import TrackObservation, TrackState, TrajectoryManager


def test_first_observation_has_no_speed() -> None:
    manager = TrajectoryManager()

    state = manager.update(1, frame=0, timestamp_sec=0.0, center_x=10, center_y=20)

    assert state.pixel_speed is None
    assert state.stationary_duration == 0.0
    assert list(state.history) == [TrackObservation(0, 0.0, 10, 20)]


def test_pixel_speed_uses_euclidean_distance_and_elapsed_time() -> None:
    manager = TrajectoryManager(
        stationary_speed_threshold=3.0,
        max_observation_gap_sec=3.0,
    )
    manager.update(1, frame=0, timestamp_sec=0.0, center_x=0, center_y=0)

    state = manager.update(1, frame=1, timestamp_sec=2.0, center_x=3, center_y=4)

    assert state.pixel_speed == pytest.approx(2.5)
    assert state.stationary_duration == 2.0


def test_movement_resets_stationary_duration() -> None:
    manager = TrajectoryManager(stationary_speed_threshold=3.0)
    manager.update(1, frame=0, timestamp_sec=0.0, center_x=10, center_y=10)
    manager.update(1, frame=1, timestamp_sec=0.5, center_x=10, center_y=10)

    state = manager.update(1, frame=2, timestamp_sec=1.0, center_x=20, center_y=10)

    assert state.pixel_speed == pytest.approx(20.0)
    assert state.stationary_duration == 0.0


def test_stationary_duration_accumulates_across_small_jitter() -> None:
    manager = TrajectoryManager(stationary_speed_threshold=3.0)
    manager.update(1, frame=0, timestamp_sec=0.0, center_x=10, center_y=10)
    manager.update(1, frame=1, timestamp_sec=0.5, center_x=11, center_y=10)

    state = manager.update(1, frame=2, timestamp_sec=1.0, center_x=12, center_y=10)

    assert state.pixel_speed == pytest.approx(2.0)
    assert state.stationary_duration == pytest.approx(1.0)


def test_tracks_keep_independent_histories() -> None:
    manager = TrajectoryManager()

    manager.update(1, frame=0, timestamp_sec=0.0, center_x=10, center_y=10)
    manager.update(2, frame=0, timestamp_sec=0.0, center_x=100, center_y=100)
    manager.update(1, frame=1, timestamp_sec=0.5, center_x=11, center_y=10)

    assert len(manager.tracks[1].history) == 2
    assert len(manager.tracks[2].history) == 1
    assert manager.tracks[1].history[-1].center_x == 11
    assert manager.tracks[2].history[-1].center_x == 100


def test_history_discards_oldest_observations_at_limit() -> None:
    manager = TrajectoryManager(history_size=3)

    for frame in range(5):
        manager.update(
            1,
            frame=frame,
            timestamp_sec=frame * 0.5,
            center_x=frame,
            center_y=0,
        )

    assert [item.frame for item in manager.tracks[1].history] == [2, 3, 4]


def test_long_detection_gap_resets_unreliable_metrics() -> None:
    manager = TrajectoryManager(
        stationary_speed_threshold=3.0,
        max_observation_gap_sec=1.0,
    )
    manager.update(1, frame=0, timestamp_sec=0.0, center_x=10, center_y=10)
    manager.update(1, frame=1, timestamp_sec=0.5, center_x=10, center_y=10)

    state = manager.update(1, frame=10, timestamp_sec=3.0, center_x=10, center_y=10)

    assert state.pixel_speed is None
    assert state.stationary_duration == 0.0


def test_rejects_non_increasing_timestamps() -> None:
    state = TrackState(track_id=1, history_size=10)
    state.update(TrackObservation(0, 1.0, 10, 10), 3.0, 1.0)

    with pytest.raises(ValueError, match="timestamps must increase"):
        state.update(TrackObservation(1, 1.0, 11, 10), 3.0, 1.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"history_size": 1},
        {"stationary_speed_threshold": -1.0},
        {"max_observation_gap_sec": 0.0},
    ],
)
def test_rejects_invalid_manager_configuration(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        TrajectoryManager(**kwargs)
