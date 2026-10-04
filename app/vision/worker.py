import logging
import re
import threading
import time

import cv2
import numpy as np

from .rules import ComplianceEngine
from .sources import DemoSource, open_capture
from .types import Capabilities, FrameResult

log = logging.getLogger("safetycheck.worker")
MAX_W = 960
# BGR
COLORS = {"safe": (94, 197, 34), "partial": (11, 158, 245), "unsafe": (68, 68, 239), "unknown": (160, 160, 160)}


def _label(p) -> str:
    def m(v):
        return "?" if v is None else ("+" if v else "-")
    return f"#{p.id} H{m(p.helmet)} V{m(p.vest)}"


def draw(frame, result: FrameResult, ppe_dets, demo: bool):
    for d in ppe_dets:
        if d.cls in ("helmet", "vest"):
            x1, y1, x2, y2 = map(int, d.box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 200, 60) if d.cls == "helmet" else (200, 90, 255), 1)
    for p in result.persons:
        x1, y1, x2, y2 = map(int, p.box)
        c = COLORS[p.status]
        cv2.rectangle(frame, (x1, y1), (x2, y2), c, 2)
        txt = _label(p)
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        ty = max(y1, th + 8)
        cv2.rectangle(frame, (x1, ty - th - 8), (x1 + tw + 8, ty), c, -1)
        cv2.putText(frame, txt, (x1 + 4, ty - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (15, 15, 15), 1, cv2.LINE_AA)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S") + ("  DEMO" if demo else "")
    cv2.putText(frame, stamp, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, stamp, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 235, 235), 1, cv2.LINE_AA)


def no_signal_frame(text="NO SIGNAL") -> np.ndarray:
    img = np.full((540, MAX_W, 3), 24, np.uint8)
    (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)
    cv2.putText(img, text, ((MAX_W - tw) // 2, 280), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (110, 110, 120), 2, cv2.LINE_AA)
    return img


class CameraWorker(threading.Thread):
    def __init__(self, rt, cam):
        super().__init__(daemon=True, name=f"cam-{cam.id}")
        self.rt = rt
        self.id, self.name_, self.source = cam.id, cam.name, cam.source
        self.require_helmet, self.require_vest = cam.require_helmet, cam.require_vest
        self.is_demo = cam.source.strip().lower() == "demo"
        self.stop_event = threading.Event()
        self.cond = threading.Condition()
        self.jpeg: bytes | None = None
        self.seq = 0
        self.online = False
        self.fps = 0.0
        self.persons: list[dict] = []
        self.counts = {"total": 0, "safe": 0, "partial": 0, "unsafe": 0, "unknown": 0}
        self.engine = ComplianceEngine()

    # -- frame sharing -------------------------------------------------------
    def _publish_frame(self, frame, quality: int) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
        if ok:
            with self.cond:
                self.jpeg, self.seq = buf.tobytes(), self.seq + 1
                self.cond.notify_all()

    def wait_frame(self, last_seq: int, timeout: float = 2.0):
        with self.cond:
            if self.seq == last_seq:
                self.cond.wait(timeout)
            return self.seq, self.jpeg

    def stop(self) -> None:
        self.stop_event.set()

    # -- main loop -------------------------------------------------------------
    def run(self) -> None:
        backoff = 1.0
        while not self.stop_event.is_set():
            try:
                streamed = self._session()
                backoff = 1.0 if streamed else min(backoff * 2, 15)
            except Exception:  # noqa: BLE001
                log.exception("camera %s crashed", self.id)
                backoff = min(backoff * 2, 15)
            self._set_online(False)
            self._publish_frame(no_signal_frame(), 60)
            self.stop_event.wait(backoff)

    def _set_online(self, v: bool) -> None:
        if v != self.online:
            self.online = v
            self.rt.hub.publish_threadsafe({"t": "cam", "cam": self.id, "online": v})

    def _session(self) -> bool:
        """Stream until the source fails. Returns True if at least one frame was received."""
        demo = DemoSource() if self.is_demo else None
        cap = None if demo else open_capture(self.source)
        if cap is not None and not cap.isOpened():
            log.warning("camera %s: cannot open %r", self.id, self.source)
            return False
        is_file = cap is not None and not re.match(r"^(\d+|\w+://.*)$", self.source.strip())
        frame_dt = 1.0 / ((cap.get(cv2.CAP_PROP_FPS) or 25.0) if is_file else 25.0)
        next_frame = time.monotonic()
        streamed = False
        last_detect = last_pub = last_live = last_sample = 0.0
        fps_n, fps_t0 = 0, time.monotonic()
        result, dets = FrameResult(), []
        read_fail = 0
        try:
            while not self.stop_event.is_set():
                if demo:
                    time.sleep(1 / 15)
                    ok, frame, hint = demo.read()
                else:
                    ok, frame = cap.read()
                    hint = None
                    if not ok and is_file and streamed:  # end of a video file: loop it
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    if not ok:
                        read_fail += 1
                        if read_fail > 20:
                            return streamed
                        time.sleep(0.05)
                        continue
                    if is_file:  # play files at their native speed
                        next_frame += frame_dt
                        delay = next_frame - time.monotonic()
                        if delay > 0:
                            time.sleep(delay)
                        else:
                            next_frame = time.monotonic()
                read_fail = 0
                streamed = True
                self._set_online(True)
                h, w = frame.shape[:2]
                if w > MAX_W:
                    frame = cv2.resize(frame, (MAX_W, int(h * MAX_W / w)), interpolation=cv2.INTER_AREA)
                    h, w = frame.shape[:2]
                now = time.monotonic()
                cfg = self.rt.settings.all()
                detector = self.rt.detector_for(demo is not None)
                if detector is not None and now - last_detect >= 1.0 / cfg["detect_fps"]:
                    last_detect = now
                    dets = detector.detect(frame, cfg["conf_threshold"], hint)
                    result = self.engine.process(
                        dets, h, now, caps=detector.caps, require_helmet=self.require_helmet,
                        require_vest=self.require_vest, violation_seconds=cfg["violation_seconds"],
                        cooldown_seconds=cfg["cooldown_seconds"], min_person_height=cfg["min_person_height"])
                    self._update_counts(result)
                    raw = frame.copy() if result.alarms else None
                    annotated = None
                    for ev in result.alarms:
                        if annotated is None:
                            annotated = frame.copy()
                            draw(annotated, result, dets, self.is_demo)
                        self.rt.on_alarm(self, ev, annotated, raw)
                elif detector is None:
                    result, dets = FrameResult(), []
                    self._update_counts(result)
                if now - last_sample >= 1.0:
                    last_sample = now
                    known = [p for p in result.persons if p.status != "unknown"]
                    if known:
                        self.rt.add_sample(self.id, len(known), sum(p.status == "safe" for p in known))
                fps_n += 1
                if now - last_pub >= 1 / 15:
                    last_pub = now
                    out = frame
                    draw(out, result, dets, self.is_demo)
                    self._publish_frame(out, cfg["stream_quality"])
                if now - last_live >= 0.25:
                    last_live = now
                    el = now - fps_t0
                    if el >= 1.0:
                        self.fps, fps_n, fps_t0 = fps_n / el, 0, now
                    self.rt.hub.publish_threadsafe({
                        "t": "live", "cam": self.id, "online": True, "fps": round(self.fps, 1),
                        "counts": self.counts, "persons": self.persons})
            return streamed
        finally:
            if cap is not None:
                cap.release()

    def _update_counts(self, result: FrameResult) -> None:
        c = {"total": len(result.persons), "safe": 0, "partial": 0, "unsafe": 0, "unknown": 0}
        for p in result.persons:
            c[p.status] += 1
        self.counts = c
        self.persons = [p.to_json() for p in result.persons]
