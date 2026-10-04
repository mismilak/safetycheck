import logging
import threading
from pathlib import Path

from ..config import config
from .types import Capabilities, Det, canonical

log = logging.getLogger("safetycheck.detector")


class YoloDetector:
    """Wraps an Ultralytics model. A PPE model gives helmet/vest capability; a plain COCO model is person-only."""

    def __init__(self, path: Path, label: str):
        from ultralytics import YOLO

        self.model = YOLO(str(path))
        self.label = label
        self.path = path
        self._lock = threading.Lock()  # one inference at a time, shared by all cameras
        self.class_map = {i: canonical(n) for i, n in self.model.names.items()}
        found = {c for c in self.class_map.values() if c}
        self.caps = Capabilities(person="person" in found,
                                 helmet=bool(found & {"helmet", "no_helmet"}),
                                 vest=bool(found & {"vest", "no_vest"}))
        self.model_names = sorted(self.model.names.values())

    def detect(self, frame, conf: float, hint=None) -> list[Det]:
        with self._lock:
            r = self.model.predict(frame, conf=conf, imgsz=config.imgsz, device=config.device, verbose=False)[0]
        out = []
        if r.boxes is None:
            return out
        for cls, cf, xyxy in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
            c = self.class_map.get(int(cls))
            if c:
                out.append(Det(c, float(cf), tuple(xyxy)))
        return out

    def info(self) -> dict:
        mode = "ppe" if (self.caps.helmet or self.caps.vest) else "person_only"
        return {"mode": mode, "model": self.label, "caps": vars(self.caps), "classes": self.model_names}


class DemoDetector:
    """Returns the ground-truth boxes produced by DemoSource (UI/demo & tests; no real inference)."""
    caps = Capabilities(person=True, helmet=True, vest=True)

    def detect(self, frame, conf: float, hint=None) -> list[Det]:
        return list(hint or [])

    def info(self) -> dict:
        return {"mode": "demo", "model": "demo", "caps": vars(self.caps), "classes": []}


class DetectorManager:
    """Loads the model in a background thread so the web UI starts instantly."""

    def __init__(self):
        self.detector: YoloDetector | None = None
        self.demo = DemoDetector()
        self.state = "loading"  # loading | ready | error
        self.error = ""

    def start(self) -> None:
        threading.Thread(target=self._load, daemon=True, name="detector-load").start()

    def _load(self) -> None:
        try:
            mode = config.detector
            if mode == "demo":
                self.state = "ready"
                return
            ppe = config.models_dir / config.model_path
            config.models_dir.mkdir(parents=True, exist_ok=True)
            if ppe.exists():
                self.detector = YoloDetector(ppe, ppe.name)
            elif mode == "yolo":
                raise FileNotFoundError(f"PPE model not found: {ppe}")
            else:
                log.warning("PPE model %s not found; falling back to person-only model", ppe)
                self.detector = YoloDetector(config.models_dir / config.person_model, config.person_model)
            self.state = "ready"
            log.info("detector ready: %s", self.detector.info())
        except Exception as e:  # noqa: BLE001
            self.state, self.error = "error", str(e)
            log.exception("detector failed to load")

    def info(self) -> dict:
        base = {"state": self.state, "error": self.error}
        if self.detector:
            return {**base, **self.detector.info()}
        if config.detector == "demo" and self.state == "ready":
            return {**base, **self.demo.info()}
        return {**base, "mode": "none", "model": "", "caps": {}, "classes": []}
