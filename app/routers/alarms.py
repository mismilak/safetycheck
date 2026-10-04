import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import config
from ..db import get_db
from ..deps import audit, require
from ..models import Alarm, User
from ..runtime import alarm_files, alarm_to_dict, delete_alarm_files
from ..security import ROLE_PERMS

router = APIRouter(prefix="/api/alarms", tags=["alarms"])
STATUSES = {"new", "ack", "false_positive"}


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, "فرمت تاریخ نامعتبر است")


def filtered(db: Session, status=None, kind=None, camera_id=None, frm=None, to=None, severity=None):
    q = db.query(Alarm)
    if status:
        q = q.filter(Alarm.status == status)
    if kind:
        q = q.filter(Alarm.kind == kind)
    if severity:
        q = q.filter(Alarm.severity == severity)
    if camera_id:
        q = q.filter(Alarm.camera_id == camera_id)
    if (d := parse_dt(frm)):
        q = q.filter(Alarm.created_at >= d)
    if (d := parse_dt(to)):
        q = q.filter(Alarm.created_at < d)
    return q


@router.get("")
def list_alarms(status: str | None = None, kind: str | None = None, severity: str | None = None,
                camera_id: int | None = None, frm: str | None = None, to: str | None = None, page: int = 1,
                page_size: int = 20, _: User = Depends(require("alarms.view")), db: Session = Depends(get_db)):
    q = filtered(db, status, kind, camera_id, frm, to, severity)
    page_size = max(1, min(page_size, 100))
    total = q.count()
    rows = q.order_by(Alarm.id.desc()).offset((max(page, 1) - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [alarm_to_dict(a) for a in rows]}


@router.get("/open-count")
def open_count(_: User = Depends(require("alarms.view")), db: Session = Depends(get_db)):
    return {"count": db.query(Alarm).filter(Alarm.status == "new").count()}


@router.get("/{aid}")
def get_alarm(aid: int, _: User = Depends(require("alarms.view")), db: Session = Depends(get_db)):
    a = db.get(Alarm, aid)
    if not a:
        raise HTTPException(404, "آلارم یافت نشد")
    return alarm_to_dict(a)


@router.get("/{aid}/image")
def image(aid: int, thumb: bool = False, _: User = Depends(require("alarms.view")), db: Session = Depends(get_db)):
    a = db.get(Alarm, aid)
    if not a or not a.image:
        raise HTTPException(404, "تصویر یافت نشد")
    p = alarm_files(a)["thumb" if thumb else "full"]
    if not p.exists():
        raise HTTPException(404, "تصویر یافت نشد")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


class AlarmPatch(BaseModel):
    status: str | None = None
    note: str | None = None


def _handle(a: Alarm, user: User, status: str | None, note: str | None) -> None:
    if status:
        if status not in STATUSES:
            raise HTTPException(400, "وضعیت نامعتبر است")
        a.status = status
        a.handled_by, a.handled_at = (user.username, datetime.utcnow()) if status != "new" else ("", None)
        if status == "false_positive" and a.image:  # keep the raw frame for the next training round
            raw = alarm_files(a)["raw"]
            if raw.exists():
                config.feedback_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(raw, config.feedback_dir / f"fp_{a.id}_{a.kind}.jpg")
    if note is not None:
        a.note = note.strip()[:1000]


@router.patch("/{aid}")
def patch_alarm(aid: int, data: AlarmPatch, request: Request, user: User = Depends(require("alarms.handle")),
                db: Session = Depends(get_db)):
    a = db.get(Alarm, aid)
    if not a:
        raise HTTPException(404, "آلارم یافت نشد")
    _handle(a, user, data.status, data.note)
    db.commit()
    audit(db, user, "alarm_update", f"#{a.id} -> {a.status}", request)
    return alarm_to_dict(a)


@router.post("/ack-all")
def ack_all(request: Request, user: User = Depends(require("alarms.handle")), db: Session = Depends(get_db)):
    rows = db.query(Alarm).filter(Alarm.status == "new").all()
    for a in rows:
        _handle(a, user, "ack", None)
    db.commit()
    audit(db, user, "alarm_ack_all", str(len(rows)), request)
    return {"count": len(rows)}


@router.delete("/{aid}")
def delete_alarm(aid: int, request: Request, user: User = Depends(require("alarms.delete")),
                 db: Session = Depends(get_db)):
    a = db.get(Alarm, aid)
    if not a:
        raise HTTPException(404, "آلارم یافت نشد")
    delete_alarm_files(a)
    db.delete(a)
    db.commit()
    audit(db, user, "alarm_delete", f"#{aid}", request)
    return {"ok": True}
