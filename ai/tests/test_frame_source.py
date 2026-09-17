import ctypes
from pathlib import Path
import sys
import threading
import time

import numpy as np
import pytest


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from frame_source import (
    CameraState,
    CaptureBackend,
    RTSPFrameSource,
    SourceType,
    VLCFrameBuffer,
    VLCFrameCapture,
    VLCI420FrameBuffer,
    VLCLocalBridgeCapture,
    VideoFileSource,
    VisualFreshnessTracker,
    mask_stream_url,
    parse_capture_backend,
    parse_source_type,
    reconnect_delays,
    resolve_rtsp_url,
)
import frame_source
import process_video
from process_video import (
    RawPreviewPublisher,
    RollingRate,
    source_generation_changed,
    write_jpeg_atomic,
)


class FakeCapture:
    def __init__(self, frames, opened=True):
        self.frames = list(frames)
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        if self.frames:
            return True, self.frames.pop(0)
        return False, None

    def get(self, prop):
        values = {5: 25.0, 3: 20, 4: 10, 7: 1}
        return values.get(prop, 0)

    def set(self, prop, value):
        return True

    def release(self):
        self.released = True


class CoordinatedCapture(FakeCapture):
    def __init__(self, frame, allow_failure: threading.Event):
        super().__init__([frame])
        self.allow_failure = allow_failure

    def read(self):
        if self.frames:
            return True, self.frames.pop(0)
        self.allow_failure.wait(timeout=1.0)
        return False, None


def test_source_type_parsing_and_rejection() -> None:
    assert parse_source_type("video_file") is SourceType.VIDEO_FILE
    assert parse_source_type("RTSP") is SourceType.RTSP
    with pytest.raises(ValueError):
        parse_source_type("webcam")


def test_capture_backend_defaults_parses_and_rejects() -> None:
    assert parse_capture_backend(None) is CaptureBackend.OPENCV
    assert parse_capture_backend("opencv") is CaptureBackend.OPENCV
    assert parse_capture_backend("vlc") is CaptureBackend.VLC
    assert parse_capture_backend("AuTo") is CaptureBackend.AUTO
    with pytest.raises(ValueError, match="OPENCV, VLC, or AUTO"):
        parse_capture_backend("gui")


def test_file_source_preserves_relative_timestamp(tmp_path: Path) -> None:
    frame = np.zeros((10, 20, 3), dtype=np.uint8)
    capture = FakeCapture([frame])
    source = VideoFileSource(tmp_path / "sample.mp4", capture_factory=lambda _: capture)

    packet = source.read()

    assert packet is not None
    assert packet.timestamp == 0.0
    assert packet.frame_index == 0
    assert source.read() is None
    source.close()
    assert capture.released


def test_rtsp_uses_wall_clock_and_reports_state() -> None:
    frame = np.zeros((10, 20, 3), dtype=np.uint8)
    capture = FakeCapture([frame])
    states = []
    values = iter([1000.0, 1000.1, 1000.2, 1000.3, 1000.4])
    source = RTSPFrameSource(
        "cam-1", "rtsp://example.test/live", reconnect_enabled=False,
        capture_factory=lambda _: capture, clock=lambda: next(values),
        status_callback=lambda health: states.append(health.state),
    )

    packet = source.read(timeout=1.0)
    source.close()

    assert packet is not None
    assert packet.timestamp == pytest.approx(1000.1)
    assert packet.generation == 1
    assert CameraState.ONLINE in states
    assert CameraState.OFFLINE in states


def test_reconnect_backoff_is_bounded() -> None:
    assert reconnect_delays(2, 8, 5) == [2, 4, 8, 8, 8]


def test_rtsp_url_env_and_credential_masking() -> None:
    url = resolve_rtsp_url(
        {"rtsp_url_env": "TEST_CAMERA_URL"},
        {"TEST_CAMERA_URL": "rtsp://user:secret@10.0.0.4/stream"},
    )
    assert url.endswith("@10.0.0.4/stream")
    masked = mask_stream_url(url)
    assert masked == "rtsp://***:***@10.0.0.4/stream"
    assert "user" not in masked and "secret" not in masked


def test_generation_change_requires_temporal_state_reset() -> None:
    assert not source_generation_changed(None, 1)
    assert not source_generation_changed(1, 1)
    assert source_generation_changed(1, 2)


def test_vlc_buffer_converts_rv32_pitch_and_keeps_latest_complete_frame() -> None:
    buffer = VLCFrameBuffer()
    pitch = buffer.configure(2, 1)
    assert pitch == 32
    token, pointer = buffer.acquire()
    native = (ctypes.c_ubyte * pitch).from_address(pointer.value)
    native[:8] = [1, 2, 3, 255, 4, 5, 6, 255]
    buffer.publish(token)
    token, pointer = buffer.acquire()
    native = (ctypes.c_ubyte * pitch).from_address(pointer.value)
    native[:8] = [7, 8, 9, 255, 10, 11, 12, 255]
    buffer.publish(token)

    frame = buffer.read(0.01)
    assert frame is not None
    assert frame.shape == (1, 2, 3)
    assert frame.tolist() == [[[7, 8, 9], [10, 11, 12]]]
    assert buffer.read(0.01) is None


def test_vlc_buffer_close_wakes_blocked_reader() -> None:
    buffer = VLCFrameBuffer()
    result = []
    reader = threading.Thread(target=lambda: result.append(buffer.read(1.0)))
    reader.start()
    time.sleep(0.01)
    buffer.close()
    reader.join(timeout=0.5)
    assert not reader.is_alive()
    assert result == [None]


def test_vlc_buffer_drops_without_waiting_and_recovers() -> None:
    buffer = VLCFrameBuffer()
    buffer.configure(2, 1)
    held = [buffer.acquire() for _ in range(buffer.BUFFER_COUNT)]

    started = time.monotonic()
    dropped_token, dropped_pointer = buffer.acquire()
    assert time.monotonic() - started < 0.05
    assert dropped_token == 0
    assert dropped_pointer.value
    assert buffer.dropped_frames == 1

    buffer.publish(held[0][0])
    assert buffer.read(0.05) is not None
    next_token, _next_pointer = buffer.acquire()
    assert next_token != 0
    buffer.publish(next_token)
    assert buffer.read(0.05) is not None
    buffer.close()


def test_atomic_jpeg_publication_and_repeated_replace(tmp_path: Path) -> None:
    path = tmp_path / "latest.jpg"
    first = np.zeros((8, 8, 3), dtype=np.uint8)
    second = np.full((8, 8, 3), 255, dtype=np.uint8)
    write_jpeg_atomic(path, first)
    first_bytes = path.read_bytes()
    write_jpeg_atomic(path, second)
    second_bytes = path.read_bytes()

    assert first_bytes.startswith(b"\xff\xd8") and first_bytes.endswith(b"\xff\xd9")
    assert second_bytes.startswith(b"\xff\xd8") and second_bytes.endswith(b"\xff\xd9")
    assert first_bytes != second_bytes
    assert list(tmp_path.glob(".latest.jpg.*.tmp")) == []


def test_atomic_jpeg_cleans_temporary_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "latest.jpg"

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(process_video.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        write_jpeg_atomic(path, np.zeros((8, 8, 3), dtype=np.uint8))

    assert not path.exists()
    assert list(tmp_path.glob(".latest.jpg.*.tmp")) == []


def test_rolling_rate_uses_recent_window_and_decays() -> None:
    rate = RollingRate(5.0)
    for timestamp in (10.0, 11.0, 12.0, 13.0, 14.0):
        rate.mark(timestamp)
    assert rate.value(14.0) == pytest.approx(1.0)
    assert rate.value(20.0) == 0.0


def test_visual_freshness_arms_after_motion_then_detects_stuck_source() -> None:
    tracker = VisualFreshnessTracker(
        stale_after_seconds=2.0, minimum_similar_frames=2, changes_to_arm=3
    )
    for index in range(3):
        tracker.observe(np.full((20, 20, 3), index * 20, dtype=np.uint8), float(index))
    frozen = np.full((20, 20, 3), 40, dtype=np.uint8)
    tracker.observe(frozen, 3.0)
    tracker.observe(frozen, 4.1)
    assert tracker.armed
    assert tracker.is_stuck(4.1)


def test_visual_freshness_does_not_reject_never_changing_scene() -> None:
    tracker = VisualFreshnessTracker(
        stale_after_seconds=1.0, minimum_similar_frames=2, changes_to_arm=3
    )
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    for timestamp in range(10):
        tracker.observe(frame, float(timestamp))
    assert not tracker.armed
    assert not tracker.is_stuck(10.0)


def test_raw_preview_publisher_is_rate_limited_and_uses_source_frame(
    tmp_path: Path,
) -> None:
    publisher = RawPreviewPublisher(tmp_path / "preview.jpg", fps=10.0)
    first = np.zeros((20, 20, 3), dtype=np.uint8)
    second = np.full((20, 20, 3), 255, dtype=np.uint8)
    try:
        assert publisher(first, 1.0, 0)
        for _ in range(50):
            if (tmp_path / "preview.jpg").exists():
                break
            time.sleep(0.01)
        original = (tmp_path / "preview.jpg").read_bytes()
        assert not publisher(second, 1.05, 1)
        time.sleep(0.03)
        assert (tmp_path / "preview.jpg").read_bytes() == original
        assert publisher(second, 1.11, 2)
        for _ in range(50):
            if (tmp_path / "preview.jpg").read_bytes() != original:
                break
            time.sleep(0.01)
        assert (tmp_path / "preview.jpg").read_bytes() != original
    finally:
        publisher.close()


def test_vlc_bridge_restores_real_media_timestamp_pacing(monkeypatch) -> None:
    capture = VLCLocalBridgeCapture.__new__(VLCLocalBridgeCapture)
    capture._media_anchor_ms = None
    capture._wall_anchor = None
    capture._last_media_ms = None
    now = iter([10.0, 10.01])
    sleeps: list[float] = []
    monkeypatch.setattr(frame_source.time, "monotonic", lambda: next(now))
    monkeypatch.setattr(frame_source.time, "sleep", sleeps.append)

    capture._pace_media_frame(1_000.0)
    capture._pace_media_frame(1_080.0)

    assert sleeps == [pytest.approx(0.07)]


def test_rtsp_stale_capture_releases_once_and_recovers_generation() -> None:
    frame = np.zeros((10, 20, 3), dtype=np.uint8)
    allow_failure = threading.Event()
    first = CoordinatedCapture(frame, allow_failure)
    second = CoordinatedCapture(frame + 1, threading.Event())
    captures = iter([first, second])
    states: list[CameraState] = []

    source = RTSPFrameSource(
        "cam-recovery", "rtsp://example.test/live",
        reconnect_enabled=True,
        reconnect_delay_seconds=0.01,
        max_reconnect_delay_seconds=0.01,
        capture_factory=lambda _: next(captures),
        sleep=lambda _delay: None,
        status_callback=lambda health: states.append(health.state),
    )
    first_packet = source.read(timeout=1.0)
    assert first_packet is not None and first_packet.generation == 1
    allow_failure.set()
    second_packet = source.read(timeout=1.0)
    source.close()

    assert second_packet is not None and second_packet.generation == 2
    assert first.released and second.released
    assert source.health.reconnect_attempts == 1
    assert CameraState.RECONNECTING in states


def test_vlc_buffer_ignores_duplicate_and_retired_format_callbacks() -> None:
    buffer = VLCFrameBuffer()
    pitch = buffer.configure(2, 1)
    token, pointer = buffer.acquire()
    pixels = (ctypes.c_ubyte * pitch).from_address(pointer.value)
    pixels[:8] = [1, 2, 3, 255, 4, 5, 6, 255]
    buffer.publish(token)
    assert buffer.read(0.01) is not None
    buffer.publish(token)
    assert buffer.read(0.01) is None

    retired_token, _retired_pointer = buffer.acquire()
    buffer.configure(4, 2)
    buffer.publish(retired_token)
    assert buffer.read(0.01) is None


def test_vlc_i420_buffer_handles_three_aligned_planes() -> None:
    buffer = VLCI420FrameBuffer()
    buffer.configure(4, 2)
    token, planes = buffer.acquire_planes()
    y = (ctypes.c_ubyte * (buffer.pitches[0] * buffer.lines[0])).from_address(
        planes[0].value
    )
    u = (ctypes.c_ubyte * (buffer.pitches[1] * buffer.lines[1])).from_address(
        planes[1].value
    )
    v = (ctypes.c_ubyte * (buffer.pitches[2] * buffer.lines[2])).from_address(
        planes[2].value
    )
    for row in range(2):
        y[row * buffer.pitches[0]:row * buffer.pitches[0] + 4] = [100] * 4
    u[:2] = [128, 128]
    v[:2] = [128, 128]
    buffer.publish(token)
    frame = buffer.read(0.01)
    assert frame is not None
    assert frame.shape == (2, 4, 3)
    assert np.allclose(frame, 98, atol=2)


class FakeEventManager:
    def __init__(self):
        self.callback = None

    def event_attach(self, _event_type, callback):
        self.callback = callback


class FakeVLCPlayer:
    def __init__(self, publish_frame=True):
        self.publish_frame = publish_frame
        self.format_callbacks = None
        self.video_callbacks = None
        self.manager = FakeEventManager()
        self.stop_calls = 0
        self.release_calls = 0
        self.on_stop = None

    def set_media(self, media):
        self.media = media

    def video_set_callbacks(self, lock, unlock, display, _opaque):
        self.video_callbacks = (lock, unlock, display)

    def video_set_format_callbacks(self, setup, cleanup):
        self.format_callbacks = (setup, cleanup)

    def event_manager(self):
        return self.manager

    def play(self):
        if self.publish_frame:
            setup, _cleanup = self.format_callbacks
            width = ctypes.c_uint(2)
            height = ctypes.c_uint(1)
            pitches = (ctypes.c_uint * 1)()
            lines = (ctypes.c_uint * 1)()
            chroma = ctypes.create_string_buffer(4)
            assert setup(
                None, chroma, ctypes.pointer(width), ctypes.pointer(height),
                pitches, lines,
            ) == VLCFrameBuffer.BUFFER_COUNT
            lock, unlock, display = self.video_callbacks
            planes = (ctypes.c_void_p * 1)()
            token = lock(None, planes)
            pixels = (ctypes.c_ubyte * pitches[0]).from_address(planes[0])
            pixels[:8] = [10, 20, 30, 255, 40, 50, 60, 255]
            unlock(None, token, planes)
            display(None, token)
        return 0

    def stop(self):
        self.stop_calls += 1
        if self.on_stop is not None:
            self.on_stop()

    def release(self):
        self.release_calls += 1


class FakeVLCMedia:
    def __init__(self):
        self.options = []
        self.release_calls = 0

    def add_option(self, option):
        self.options.append(option)

    def release(self):
        self.release_calls += 1


class FakeVLCInstance:
    def __init__(self, player):
        self.player = player
        self.media = FakeVLCMedia()
        self.release_calls = 0

    def media_new(self, _url):
        return self.media

    def media_player_new(self):
        return self.player

    def release(self):
        self.release_calls += 1


class FakeVLCModule:
    class EventType:
        MediaPlayerEncounteredError = 1

    def __init__(self, publish_frame=True):
        self.player = FakeVLCPlayer(publish_frame=publish_frame)
        self.instance = FakeVLCInstance(self.player)

    def Instance(self, *_args):
        return self.instance


def test_vlc_capture_callbacks_publish_bgr_and_release_once() -> None:
    module = FakeVLCModule()
    capture = VLCFrameCapture(
        "rtsp://camera.invalid/live", 0.05, vlc_module=module,
        pixel_format="RV32", rtsp_tcp=True,
    )
    ok, frame = capture.read()
    assert ok
    assert frame.tolist() == [[[10, 20, 30], [40, 50, 60]]]
    assert ":no-audio" in module.instance.media.options
    assert ":rtsp-tcp" in module.instance.media.options
    capture.release()
    capture.release()
    assert module.player.stop_calls == 1
    assert module.player.release_calls == 1
    assert module.instance.media.release_calls == 1
    assert module.instance.release_calls == 1


def test_vlc_capture_times_out_without_frame_and_handles_playback_error() -> None:
    module = FakeVLCModule(publish_frame=False)
    capture = VLCFrameCapture(
        "rtsp://camera.invalid/live", 0.01, vlc_module=module,
        pixel_format="RV32",
    )
    assert capture.read() == (False, None)
    module.player.manager.callback(None)
    assert capture.read() == (False, None)
    capture.release()


def test_vlc_capture_keeps_callback_buffers_valid_until_player_stops() -> None:
    module = FakeVLCModule(publish_frame=False)
    capture = VLCFrameCapture(
        "rtsp://camera.invalid/live", 0.01, vlc_module=module,
        pixel_format="RV32",
    )
    capture._buffer.configure(2, 1)
    observed_pointer = []

    def final_decoder_callback():
        token, pointer = capture._buffer.acquire()
        observed_pointer.append(pointer.value)
        capture._buffer.publish(token)

    module.player.on_stop = final_decoder_callback
    capture.release()

    assert observed_pointer[0]
    assert capture._buffer.read(0.01) is None


def test_backend_selection_and_auto_fallback() -> None:
    frame = np.zeros((10, 20, 3), dtype=np.uint8)
    failed_opencv = FakeCapture([], opened=False)
    vlc_capture = FakeCapture([frame])
    calls = []

    def vlc_factory(url, **kwargs):
        calls.append((url, kwargs))
        return vlc_capture

    source = RTSPFrameSource(
        "cam-auto", "rtsp://example.test/live",
        reconnect_enabled=False,
        capture_backend=CaptureBackend.AUTO,
        capture_factory=lambda _: failed_opencv,
        vlc_capture_factory=vlc_factory,
    )
    packet = source.read(timeout=1.0)
    source.close()
    assert packet is not None
    assert failed_opencv.released
    assert calls[0][0] == "rtsp://example.test/live"
    assert calls[0][1]["frame_timeout_seconds"] == 5.0


def test_opencv_default_does_not_initialize_vlc() -> None:
    frame = np.zeros((10, 20, 3), dtype=np.uint8)
    capture = FakeCapture([frame])

    def forbidden_vlc(*_args, **_kwargs):
        raise AssertionError("VLC must not be used by the OPENCV default")

    source = RTSPFrameSource(
        "cam-default", "rtsp://example.test/live",
        reconnect_enabled=False,
        capture_factory=lambda _: capture,
        vlc_capture_factory=forbidden_vlc,
    )
    assert source.read(timeout=1.0) is not None
    source.close()
    parse_capture_backend,
