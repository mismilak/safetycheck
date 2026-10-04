"""Runtime settings stored in DB with an in-memory cache (read by camera workers)."""
import json
import threading

from .db import SessionLocal
from .models import Setting

DEFAULTS: dict = {
    "org_name": "سیف‌چک",
    "conf_threshold": 0.45,
    "violation_seconds": 3.0,
    "cooldown_seconds": 60.0,
    "min_person_height": 0.12,  # fraction of frame height; smaller persons are ignored
    "detect_fps": 8,
    "stream_quality": 70,
    "retention_days": 90,
    "telegram_enabled": False,
    "telegram_token": "",
    "telegram_chat_id": "",
    "webhook_url": "",
    "notify_min_severity": "medium",
}
SECRET_KEYS = {"telegram_token"}
LIMITS = {
    "conf_threshold": (0.1, 0.95),
    "violation_seconds": (0.5, 60),
    "cooldown_seconds": (5, 3600),
    "min_person_height": (0.0, 0.8),
    "detect_fps": (1, 30),
    "stream_quality": (30, 95),
    "retention_days": (0, 3650),
}


class SettingsService:
    def __init__(self):
        self._lock = threading.Lock()
        self._cache = dict(DEFAULTS)
        self.reload()

    def reload(self) -> None:
        with SessionLocal() as db:
            rows = {r.key: r.value for r in db.query(Setting).all()}
        with self._lock:
            self._cache = dict(DEFAULTS)
            for k, v in rows.items():
                if k in DEFAULTS:
                    try:
                        self._cache[k] = json.loads(v)
                    except ValueError:
                        pass

    def all(self) -> dict:
        with self._lock:
            return dict(self._cache)

    def get(self, key: str):
        with self._lock:
            return self._cache.get(key, DEFAULTS.get(key))

    def update(self, values: dict) -> dict:
        clean = {}
        for k, v in values.items():
            if k not in DEFAULTS:
                continue
            default = DEFAULTS[k]
            if k in SECRET_KEYS and (v is None or str(v).startswith("•")):
                continue  # masked placeholder -> keep stored secret
            if isinstance(default, bool):
                v = bool(v)
            elif isinstance(default, (int, float)):
                v = float(v) if isinstance(default, float) else int(float(v))
                lo, hi = LIMITS.get(k, (None, None))
                if lo is not None:
                    v = max(lo, min(hi, v))
            else:
                v = str(v or "").strip()[:500]
            clean[k] = v
        with SessionLocal() as db:
            for k, v in clean.items():
                row = db.get(Setting, k)
                if row:
                    row.value = json.dumps(v)
                else:
                    db.add(Setting(key=k, value=json.dumps(v)))
            db.commit()
        self.reload()
        return clean

    def public(self, reveal_secrets: bool = False) -> dict:
        d = self.all()
        for k in SECRET_KEYS:
            if d.get(k) and not reveal_secrets:
                d[k] = "••••••••"
        return d
