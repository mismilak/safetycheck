import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, require
from ..models import Camera, User
from ..runtime import get_runtime
from ..security import ROLE_PERMS
from ..vision.sources import open_capture

router = APIRouter(prefix="/api/cameras", tags=["cameras"])
SRC_RE = re.compile(r"^(\d{1,2}|demo|(rtsps?|https?|rtmp)://\S+|\S+\.(mp4|avi|mkv|mov|m4v))$", re.I)


def mask(src: str) -> str:
    return re.sub(r"://[^/@\s]+@", "://***@", src)


def cam_json(c: Camera, user: User) -> dict:
    full = "cameras.manage" in ROLE_PERMS.get(user.role, set())
    st = get_runtime().camera_status(c.id)
    return {"id": c.id, "name": c.name, "location": c.location, "enabled": c.enabled,
            "require_helmet": c.require_helmet, "require_vest": c.require_vest,
            "source": c.source if full else mask(c.source), "online": st["online"], "fps": st["fps"],
            "counts": st["counts"], "stats": st["stats"]}


class CameraIn(BaseModel):
    name: str
    location: str = ""
    source: str
    enabled: bool = True
    require_helmet: bool = True
    require_vest: bool = True


def _validate(d: CameraIn) -> None:
    if not d.name.strip():
        raise HTTPException(400, "نام دوربین الزامی است")
    if not SRC_RE.match(d.source.strip()):
        raise HTTPException(400, "منبع نامعتبر است: شماره وب‌کم (مثل 0)، آدرس rtsp:// یا http://، فایل ویدیو یا demo")


@router.get("")
def list_cameras(user: User = Depends(require("live.view")), db: Session = Depends(get_db)):
    return [cam_json(c, user) for c in db.query(Camera).order_by(Camera.id).all()]


@router.post("", status_code=201)
def create(data: CameraIn, request: Request, user: User = Depends(require("cameras.manage")),
           db: Session = Depends(get_db)):
    _validate(data)
    c = Camera(name=data.name.strip()[:128], location=data.location.strip()[:128], source=data.source.strip(),
               enabled=data.enabled, require_helmet=data.require_helmet, require_vest=data.require_vest)
    db.add(c)
    db.commit()
    audit(db, user, "camera_create", c.name, request)
    get_runtime().sync_cameras()
    return cam_json(c, user)


@router.put("/{cid}")
def update(cid: int, data: CameraIn, request: Request, user: User = Depends(require("cameras.manage")),
           db: Session = Depends(get_db)):
    c = db.get(Camera, cid)
    if not c:
        raise HTTPException(404, "دوربین یافت نشد")
    _validate(data)
    c.name, c.location, c.source = data.name.strip()[:128], data.location.strip()[:128], data.source.strip()
    c.enabled, c.require_helmet, c.require_vest = data.enabled, data.require_helmet, data.require_vest
    db.commit()
    audit(db, user, "camera_update", c.name, request)
    get_runtime().sync_cameras()
    return cam_json(c, user)


@router.delete("/{cid}")
def delete(cid: int, request: Request, user: User = Depends(require("cameras.manage")), db: Session = Depends(get_db)):
    c = db.get(Camera, cid)
    if not c:
        raise HTTPException(404, "دوربین یافت نشد")
    name = c.name
    db.delete(c)
    db.commit()
    audit(db, user, "camera_delete", name, request)
    get_runtime().sync_cameras()
    return {"ok": True}


class TestIn(BaseModel):
    source: str
    camera_id: int | None = None


def _probe(source: str) -> dict:
    cap = open_capture(source)
    try:
        if not cap.isOpened():
            return {"ok": False, "message": "اتصال برقرار نشد"}
        ok, frame = cap.read()
        if not ok:
            return {"ok": False, "message": "اتصال برقرار شد اما تصویری دریافت نشد"}
        h, w = frame.shape[:2]
        return {"ok": True, "message": f"اتصال موفق ({w}×{h})"}
    finally:
        cap.release()


@router.post("/test")
async def test(data: TestIn, _: User = Depends(require("cameras.manage"))):
    src = data.source.strip()
    if not SRC_RE.match(src):
        raise HTTPException(400, "منبع نامعتبر است")
    if src.lower() == "demo":
        return {"ok": True, "message": "منبع نمایشی آماده است"}
    for w in get_runtime().workers.values():
        if w.source == src and w.online:
            return {"ok": True, "message": "این منبع هم‌اکنون فعال و آنلاین است"}
    try:
        return await asyncio.wait_for(asyncio.to_thread(_probe, src), 15)
    except asyncio.TimeoutError:
        return {"ok": False, "message": "زمان اتصال به پایان رسید"}
