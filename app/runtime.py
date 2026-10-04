"""Owns camera workers, alarm persistence, stats aggregation and retention cleanup."""
import logging
import shutil
import threading
import time
from datetime import datetime, timedelta

import cv2

from .config import config
from .db import SessionLocal
from .hub import hub
from .models import Alarm, Camera, HourStat
from .notifier import Notifier
from .settings_service import SettingsService
from .vision.detector import DetectorManager
from .vision.worker import CameraWorker

log = logging.getLogger("safetycheck.runtime")


def alarm_to_dict(a: Alarm, camera_name: str | None = None) -> dict:
    return {
        "id": a.id, "camera_id": a.camera_id, "camera": camera_name or (a.camera.name if a.camera else ""),
        "track_id": a.track_id, "kind": a.kind, "severity": a.severity, "duration": round(a.duration, 1),
        "created_at": a.created_at.isoformat() + "Z", "status": a.status, "handled_by": a.handled_by,
        "handled_at": a.handled_at.isoformat() + "Z" if a.handled_at else None, "note": a.note,
        "has_image": bool(a.image),
    }


class Runtime:
    def __init__(self):
        self.settings = SettingsService()
        self.detectors = DetectorManager()
        self.hub = hub
        self.notifier = Notifier(self.settings)
        self.workers: dict[int, CameraWorker] = {}
        self._samples: dict[tuple[int, int], list[int]] = {}
        self._slock = threading.Lock()
        self._stop = threading.Event()
        self.started_at = time.time()

    # -- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        self.detectors.start()
        self.sync_cameras()
        threading.Thread(target=self._maintenance, daemon=True, name="maintenance").start()

    def stop(self) -> None:
        self._stop.set()
        ws = list(self.workers.values())
        for w in ws:
            w.stop()
        for w in ws:
            w.join(timeout=5)
        self.flush_samples()

    def detector_for(self, demo: bool):
        if demo:
            return self.detectors.demo
        return self.detectors.detector  # None while loading -> plain video

    def sync_cameras(self) -> None:
        with SessionLocal() as db:
            cams = {c.id: c for c in db.query(Camera).all()}
        for cid in list(self.workers):
            w = self.workers[cid]
            c = cams.get(cid)
            changed = c is None or not c.enabled or (c.source, c.require_helmet, c.require_vest, c.name) != (
                w.source, w.require_helmet, w.require_vest, w.name_)
            if changed:
                w.stop()
                del self.workers[cid]
        for cid, c in cams.items():
            if c.enabled and cid not in self.workers:
                w = CameraWorker(self, c)
                self.workers[cid] = w
                w.start()

    # -- alarms ----------------------------------------------------------------
    def on_alarm(self, worker: CameraWorker, ev, annotated, raw) -> None:
        now = datetime.utcnow()
        folder = config.snapshots_dir / now.strftime("%Y%m%d")
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"cam{worker.id}_{now.strftime('%H%M%S')}_{ev.track_id}_{ev.kind}"
        rel = f"{now.strftime('%Y%m%d')}/{stem}.jpg"
        cv2.imwrite(str(folder / f"{stem}.jpg"), annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        h, w = annotated.shape[:2]
        cv2.imwrite(str(folder / f"{stem}_t.jpg"), cv2.resize(annotated, (360, int(360 * h / w))),
                    [cv2.IMWRITE_JPEG_QUALITY, 70])
        if raw is not None:
            cv2.imwrite(str(folder / f"{stem}_raw.jpg"), raw, [cv2.IMWRITE_JPEG_QUALITY, 90])
        with SessionLocal() as db:
            a = Alarm(camera_id=worker.id, track_id=ev.track_id, kind=ev.kind, severity=ev.severity,
                      duration=ev.duration, image=rel, created_at=now)
            db.add(a)
            db.commit()
            payload = alarm_to_dict(a, worker.name_)
        hub.publish_threadsafe({"t": "alarm", "alarm": payload})
        self.notifier.push(payload, str(folder / f"{stem}.jpg"))
        log.info("ALARM cam=%s track=%s kind=%s", worker.id, ev.track_id, ev.kind)

    # -- stats -----------------------------------------------------------------
    def add_sample(self, cam_id: int, persons: int, safe: int) -> None:
        hour = int(time.time() // 3600 * 3600)
        with self._slock:
            s = self._samples.setdefault((hour, cam_id), [0, 0])
            s[0] += persons
            s[1] += safe

    def flush_samples(self) -> None:
        with self._slock:
            data, self._samples = self._samples, {}
        if not data:
            return
        with SessionLocal() as db:
            for (hour, cam), (persons, safe) in data.items():
                row = db.query(HourStat).filter_by(hour_ts=hour, camera_id=cam).one_or_none()
                if row:
                    row.persons += persons
                    row.safe += safe
                else:
                    db.add(HourStat(hour_ts=hour, camera_id=cam, persons=persons, safe=safe))
            db.commit()

    # -- background maintenance --------------------------------------------------
    def _maintenance(self) -> None:
        last_cleanup = 0.0
        while not self._stop.wait(20):
            try:
                self.flush_samples()
                if time.time() - last_cleanup > 3600:
                    last_cleanup = time.time()
                    self.cleanup()
            except Exception:  # noqa: BLE001
                log.exception("maintenance failed")

    def cleanup(self) -> None:
        days = int(self.settings.get("retention_days"))
        if days <= 0:
            return
        cutoff = datetime.utcnow() - timedelta(days=days)
        with SessionLocal() as db:
            old = db.query(Alarm).filter(Alarm.created_at < cutoff).all()
            for a in old:
                delete_alarm_files(a)
                db.delete(a)
            db.query(HourStat).filter(HourStat.hour_ts < int(cutoff.timestamp()) - 86400 * 365).delete()
            db.commit()
        if config.snapshots_dir.exists():
            for d in config.snapshots_dir.iterdir():
                if d.is_dir() and not any(d.iterdir()):
                    shutil.rmtree(d, ignore_errors=True)

    def camera_status(self, cam_id: int) -> dict:
        w = self.workers.get(cam_id)
        if not w:
            return {"online": False, "fps": 0, "counts": None}
        return {"online": w.online, "fps": round(w.fps, 1), "counts": w.counts}


def alarm_files(a: Alarm) -> dict[str, "Path"]:  # noqa: F821
    base = config.snapshots_dir / a.image
    return {"full": base, "thumb": base.with_name(base.stem + "_t.jpg"), "raw": base.with_name(base.stem + "_raw.jpg")}


def delete_alarm_files(a: Alarm) -> None:
    if not a.image:
        return
    for p in alarm_files(a).values():
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global runtime
    if runtime is None:
        runtime = Runtime()
    return runtime
