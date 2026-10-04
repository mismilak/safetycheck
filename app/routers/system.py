import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import VERSION, config
from ..db import get_db
from ..deps import audit, require
from ..models import User
from ..runtime import get_runtime

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/public")
def public():
    return {"org_name": get_runtime().settings.get("org_name"), "version": VERSION}


@router.get("/system/status")
def status(_: User = Depends(require("live.view"))):
    rt = get_runtime()
    return {"version": VERSION, "uptime": int(time.time() - rt.started_at), "detector": rt.detectors.info(),
            "device": config.device, "cameras_online": sum(w.online for w in rt.workers.values()),
            "cameras_total": len(rt.workers)}


@router.get("/settings")
def get_settings(user: User = Depends(require("settings.view"))):
    return get_runtime().settings.public()


@router.put("/settings")
def put_settings(values: dict, request: Request, user: User = Depends(require("settings.edit")),
                 db: Session = Depends(get_db)):
    if not isinstance(values, dict):
        raise HTTPException(400, "bad payload")
    changed = get_runtime().settings.update(values)
    audit(db, user, "settings_update", ",".join(k for k in changed if "token" not in k), request)
    return get_runtime().settings.public()
