"""Regression test: slow inference must not slow down or delay the live video.

A fake camera produces 25 fps in real time and, like an RTSP/FFmpeg socket buffer, keeps everything we have not read yet.
The detector takes 0.4 s per frame (a slow CPU). The video shown to the user must still run smoothly and stay current.
"""
import collections
import struct
import threading
import time
from types import SimpleNamespace

import numpy as np

import app.vision.worker as worker_mod
from app.vision.types import Capabilities

CFG = {"detect_fps": 8, "conf_threshold": 0.4, "violation_seconds": 3.0, "cooldown_seconds": 60.0,
       "min_person_height": 0.0, "stream_quality": 60}


class FakeCap:
    """Real-time producer + FIFO backlog (a read returns the OLDEST unread frame, exactly like a socket buffer)."""

    def __init__(self, fps=25):
        self.fps, self.q, self.cond, self.stop = fps, collections.deque(), threading.Condition(), False
        threading.Thread(target=self._produce, daemon=True).start()

    def _produce(self):
        nxt = time.monotonic()
        while not self.stop:
            f = np.zeros((360, 640, 3), np.uint8)
            f[0, 0:4, 0] = np.frombuffer(struct.pack("<I", int(time.monotonic() * 1000) & 0xFFFFFFFF), np.uint8)
            with self.cond:
                self.q.append(f)
                self.cond.notify()
            nxt += 1 / self.fps
            time.sleep(max(0, nxt - time.monotonic()))

    def isOpened(self):
        return True

    def read(self):
        with self.cond:
            while not self.q and not self.stop:
                self.cond.wait(0.5)
            return (True, self.q.popleft()) if self.q else (False, None)

    def get(self, _):
        return float(self.fps)

    def set(self, *_):
        return True

    def release(self):
        self.stop = True


class SlowDetector:
    caps = Capabilities(person=True, helmet=True, vest=True)

    def __init__(self, delay):
        self.delay, self.calls = delay, 0

    def detect(self, frame, conf, hint=None):
        self.calls += 1
        time.sleep(self.delay)
        return []


def run_worker(delay, seconds=7.0):
    det = SlowDetector(delay)
    rt = SimpleNamespace(settings=SimpleNamespace(all=lambda: dict(CFG)), hub=SimpleNamespace(publish_threadsafe=lambda m: None),
                         detector_for=lambda demo: det, on_alarm=lambda *a, **k: None, add_sample=lambda *a: None)
    cam = SimpleNamespace(id=1, name="t", source="fake://cam", require_helmet=True, require_vest=True)
    fake = FakeCap()
    orig_open = worker_mod.open_capture
    worker_mod.open_capture = lambda src: fake
    w = worker_mod.CameraWorker(rt, cam)
    ages, orig_pub = [], w._publish_frame

    def spy(frame, q):
        if frame.shape[:2] == (360, 640):
            ts = struct.unpack("<I", bytes(frame[0, 0:4, 0]))[0]
            ages.append(((int(time.monotonic() * 1000) & 0xFFFFFFFF) - ts) / 1000)
        orig_pub(frame, q)

    w._publish_frame = spy
    try:
        w.start()
        time.sleep(seconds)
    finally:
        w.stop()
        fake.release()
        w.join(timeout=5)
        worker_mod.open_capture = orig_open
    return len(ages) / seconds, ages, det.calls / seconds


def test_slow_detector_does_not_throttle_or_delay_the_stream():
    pub_fps, ages, det_fps = run_worker(delay=0.4)
    late = sorted(ages)[int(len(ages) * 0.9)] if ages else 99
    print(f"stream {pub_fps:.1f} fps | 90th percentile frame age {late:.2f}s | detections {det_fps:.1f}/s")
    assert pub_fps >= 17, f"video throttled to {pub_fps:.1f} fps by slow inference"
    assert late < 0.6, f"video is {late:.1f}s behind the camera"
    assert 1.5 <= det_fps <= 3.2  # detection simply runs as fast as the CPU allows
