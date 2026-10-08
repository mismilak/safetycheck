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
    """Two decoupled loops per camera so slow inference can never slow down or delay the video:

    * this thread (reader/publisher): drains the camera as fast as it delivers, draws the LATEST detection result on the
      frame and publishes it (<= 20 fps). It always shows the newest camera frame.
    * inference thread: repeatedly takes the newest frame (older ones are skipped, never queued), runs the detector and the
      rules, saves alarms. Its speed only changes how often the boxes update.
    """

    def __init__(self, rt, cam):
        super().__init__(daemon=True, name=f"cam-{cam.id}")
        self.rt = rt
        self.id, self.name_, self.source = cam.id, cam.name, cam.source
        self.require_helmet, self.require_vest = cam.require_helmet, cam.require_vest
        self.is_demo = cam.source.strip().lower() == "demo"
        self.stop_event = threading.Event()
        self.cond = threading.Condition()  # published JPEG
        self.jpeg: bytes | None = None
        self.seq = 0
        self.online = False
        self.fps = 0.0  # frames per second shown to viewers
        self.persons: list[dict] = []
        self.counts = {"total": 0, "safe": 0, "partial": 0, "unsafe": 0, "unknown": 0}
        self.stats = {"read_fps": 0.0, "infer_fps": 0.0, "infer_ms": 0.0, "res": ""}
        self.engine = ComplianceEngine()
        self._rlock = threading.Lock()  # latest detection result (written by inference, read by publisher)
        self._result, self._dets = FrameResult(), []
        self._icond = threading.Condition()  # newest raw frame handed to the inference thread
        self._latest = None  # (id, frame, hint)
        self._frame_id = 0
        self._infer_thread: threading.Thread | None = None

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
        with self._icond:
            self._icond.notify_all()

    # -- main loop -------------------------------------------------------------
    def run(self) -> None:
        self._infer_thread = threading.Thread(target=self._infer_loop, daemon=True, name=f"infer-{self.id}")
        self._infer_thread.start()
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
        self._infer_thread.join(timeout=5)

    def join(self, timeout: float | None = None) -> None:
        super().join(timeout)

    def _set_online(self, v: bool) -> None:
        if v != self.online:
            self.online = v
            self.rt.hub.publish_threadsafe({"t": "cam", "cam": self.id, "online": v})

    def _session(self) -> bool:
        """Read/publish until the source fails. Returns True if at least one frame was received."""
        demo = DemoSource() if self.is_demo else None
        cap = None if demo else open_capture(self.source)
        if cap is not None and not cap.isOpened():
            log.warning("camera %s: cannot open %r", self.id, self.source)
            return False
        is_file = cap is not None and not re.match(r"^(\d+|\w+://.*)$", self.source.strip())
        frame_dt = 1.0 / ((cap.get(cv2.CAP_PROP_FPS) or 25.0) if is_file else 25.0)
        next_frame = time.monotonic()
        streamed = False
        next_pub = last_live = 0.0
        read_n = pub_n = 0
        t0 = time.monotonic()
        read_fail = 0
        try:
            while not self.stop_event.is_set():
                hint = None
                if demo:
                    time.sleep(1 / 15)
                    ok, frame, hint = demo.read()
                else:
                    ok, frame = cap.read()
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
                read_n += 1
                self._set_online(True)
                h, w = frame.shape[:2]
                if w > MAX_W:
                    frame = cv2.resize(frame, (MAX_W, int(h * MAX_W / w)), interpolation=cv2.INTER_AREA)
                    h, w = frame.shape[:2]
                if self.stats["res"] == "" or self.stats["res"].startswith("src"):
                    self.stats["res"] = f"{w}x{h}"
                with self._icond:  # hand the newest frame to the detector (it skips any it was too slow to take)
                    self._frame_id += 1
                    self._latest = (self._frame_id, frame, hint)
                    self._icond.notify()
                now = time.monotonic()
                if now >= next_pub:  # cap at 20 fps; an accumulating schedule (not "now - last >= 50 ms") so a 25 fps camera isn't halved
                    next_pub = max(next_pub + 1 / 20, now)
                    with self._rlock:
                        result, dets = self._result, self._dets
                    out = frame.copy()
                    draw(out, result, dets, self.is_demo)
                    self._publish_frame(out, self.rt.settings.all()["stream_quality"])
                    pub_n += 1
                if now - last_live >= 0.25:
                    last_live = now
                    el = now - t0
                    if el >= 1.0:
                        self.fps, self.stats["read_fps"] = pub_n / el, read_n / el
                        read_n = pub_n = 0
                        t0 = now
                    self.rt.hub.publish_threadsafe({
                        "t": "live", "cam": self.id, "online": True, "fps": round(self.fps, 1), "stats": self.stats,
                        "counts": self.counts, "persons": self.persons})
            return streamed
        finally:
            if cap is not None:
                cap.release()

    # -- inference loop ----------------------------------------------------------
    def _infer_loop(self) -> None:
        last_id, last_sample, last_start = 0, 0.0, 0.0
        ema_ms, done_n, t0 = 0.0, 0, time.monotonic()
        while not self.stop_event.is_set():
            try:
                cfg = self.rt.settings.all()
                wait = last_start + 1.0 / cfg["detect_fps"] - time.monotonic()
                if wait > 0:  # honour the configured max detections/second (saves CPU)
                    self.stop_event.wait(wait)
                with self._icond:
                    while (self._latest is None or self._latest[0] == last_id) and not self.stop_event.is_set():
                        self._icond.wait(0.5)
                    if self.stop_event.is_set():
                        break
                    last_id, frame, hint = self._latest
                if not self.online:
                    continue
                detector = self.rt.detector_for(self.is_demo)
                last_start = now = time.monotonic()
                if detector is None:  # model still loading: plain video
                    self._store(FrameResult(), [])
                    self.stop_event.wait(0.3)
                    continue
                h = frame.shape[0]
                dets = detector.detect(frame, cfg["conf_threshold"], hint)
                result = self.engine.process(
                    dets, h, now, caps=detector.caps, require_helmet=self.require_helmet, require_vest=self.require_vest,
                    violation_seconds=cfg["violation_seconds"], cooldown_seconds=cfg["cooldown_seconds"],
                    min_person_height=cfg["min_person_height"])
                self._store(result, dets)
                if result.alarms:
                    annotated = frame.copy()
                    draw(annotated, result, dets, self.is_demo)
                    for ev in result.alarms:
                        self.rt.on_alarm(self, ev, annotated, frame)
                end = time.monotonic()
                ema_ms = (end - now) * 1000 if ema_ms == 0 else ema_ms * 0.8 + (end - now) * 1000 * 0.2
                done_n += 1
                if end - t0 >= 1.0:
                    self.stats["infer_fps"], self.stats["infer_ms"] = done_n / (end - t0), ema_ms
                    done_n, t0 = 0, end
                if end - last_sample >= 1.0:
                    last_sample = end
                    known = [p for p in result.persons if p.status != "unknown"]
                    if known:
                        self.rt.add_sample(self.id, len(known), sum(p.status == "safe" for p in known))
            except Exception:  # noqa: BLE001
                log.exception("camera %s inference failed", self.id)
                self.stop_event.wait(1.0)

    def _store(self, result: FrameResult, dets) -> None:
        with self._rlock:
            self._result, self._dets = result, dets
        self._update_counts(result)

    def _update_counts(self, result: FrameResult) -> None:
        c = {"total": len(result.persons), "safe": 0, "partial": 0, "unsafe": 0, "unknown": 0}
        for p in result.persons:
            c[p.status] += 1
        self.counts = c
        self.persons = [p.to_json() for p in result.persons]
