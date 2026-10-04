from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require
from ..models import Alarm, Camera, HourStat, User
from ..runtime import get_runtime

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats(days: int = 7, tz_offset: int = 0, _: User = Depends(require("stats.view")), db: Session = Depends(get_db)):
    """tz_offset: JS Date.getTimezoneOffset() (minutes behind UTC; Tehran = -210)."""
    days = max(1, min(days, 90))
    off = timedelta(minutes=-tz_offset)
    now_local = datetime.utcnow() + off
    start_local = datetime(now_local.year, now_local.month, now_local.day) - timedelta(days=days - 1)
    start_utc = start_local - off

    alarms = db.query(Alarm.created_at, Alarm.kind, Alarm.severity, Alarm.camera_id, Alarm.status) \
        .filter(Alarm.created_at >= start_utc).all()
    hourly = [0] * 24
    kinds = {"no_helmet": 0, "no_vest": 0, "no_both": 0}
    per_cam: dict[int, int] = {}
    per_day: dict[str, int] = {}
    high = new = 0
    for created, kind, sev, cam, status in alarms:
        loc = created + off
        hourly[loc.hour] += 1
        per_day[loc.strftime("%Y-%m-%d")] = per_day.get(loc.strftime("%Y-%m-%d"), 0) + 1
        kinds[kind] = kinds.get(kind, 0) + 1
        per_cam[cam] = per_cam.get(cam, 0) + 1
        high += sev == "high"
        new += status == "new"

    comp_day: dict[str, list[int]] = {}
    tot_p = tot_s = 0
    for h in db.query(HourStat).filter(HourStat.hour_ts >= int(start_utc.timestamp())).all():
        d = (datetime.utcfromtimestamp(h.hour_ts) + off).strftime("%Y-%m-%d")
        c = comp_day.setdefault(d, [0, 0])
        c[0] += h.persons
        c[1] += h.safe
        tot_p += h.persons
        tot_s += h.safe

    daily = []
    for i in range(days):
        d = (start_local + timedelta(days=i)).strftime("%Y-%m-%d")
        p, s = comp_day.get(d, [0, 0])
        daily.append({"date": d, "alarms": per_day.get(d, 0), "compliance": round(100 * s / p, 1) if p else None})

    cams = {c.id: c.name for c in db.query(Camera).all()}
    rt = get_runtime()
    people_now = sum((w.counts or {}).get("total", 0) for w in rt.workers.values() if w.online)
    return {
        "summary": {"alarms": len(alarms), "new": new, "high": high,
                    "compliance": round(100 * tot_s / tot_p, 1) if tot_p else None, "people_now": people_now},
        "hourly": hourly, "daily": daily, "kinds": kinds,
        "cameras": sorted(({"id": k, "name": cams.get(k, f"#{k}"), "alarms": v} for k, v in per_cam.items()),
                          key=lambda x: -x["alarms"]),
    }
