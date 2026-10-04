import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, require
from ..models import Audit, User
from ..security import ROLE_LABELS, ROLES, check_password_strength, hash_password

router = APIRouter(prefix="/api", tags=["users"])
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")


def row(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
            "role_label": ROLE_LABELS.get(u.role, u.role), "is_active": u.is_active,
            "last_login": u.last_login.isoformat() + "Z" if u.last_login else None,
            "created_at": u.created_at.isoformat() + "Z"}


class UserIn(BaseModel):
    username: str
    full_name: str = ""
    role: str = "viewer"
    password: str


class UserPatch(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


def _active_admins(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()


@router.get("/roles")
def roles(_: User = Depends(require("users.manage"))):
    return [{"id": r, "label": ROLE_LABELS[r]} for r in ROLES]


@router.get("/users")
def list_users(_: User = Depends(require("users.manage")), db: Session = Depends(get_db)):
    return [row(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users", status_code=201)
def create_user(data: UserIn, request: Request, me: User = Depends(require("users.manage")),
                db: Session = Depends(get_db)):
    username = data.username.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "نام کاربری باید ۳ تا ۳۲ کاراکتر انگلیسی (حرف، عدد، . _ -) باشد")
    if data.role not in ROLES:
        raise HTTPException(400, "نقش نامعتبر است")
    if (err := check_password_strength(data.password)):
        raise HTTPException(400, err)
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(409, "این نام کاربری قبلاً ثبت شده است")
    u = User(username=username, full_name=data.full_name.strip()[:128], role=data.role,
             password_hash=hash_password(data.password), must_change_password=True)
    db.add(u)
    db.commit()
    audit(db, me, "user_create", f"{username} ({data.role})", request)
    return row(u)


@router.patch("/users/{uid}")
def update_user(uid: int, data: UserPatch, request: Request, me: User = Depends(require("users.manage")),
                db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "کاربر یافت نشد")
    if data.role is not None:
        if data.role not in ROLES:
            raise HTTPException(400, "نقش نامعتبر است")
        if u.id == me.id and data.role != "admin":
            raise HTTPException(400, "نمی‌توانید نقش خودتان را تنزل دهید")
        u.role = data.role
    if data.is_active is not None:
        if u.id == me.id and not data.is_active:
            raise HTTPException(400, "نمی‌توانید حساب خودتان را غیرفعال کنید")
        u.is_active = data.is_active
    if data.full_name is not None:
        u.full_name = data.full_name.strip()[:128]
    if data.password:
        if (err := check_password_strength(data.password)):
            raise HTTPException(400, err)
        u.password_hash = hash_password(data.password)
        u.must_change_password = True
    db.flush()
    if _active_admins(db) == 0:
        db.rollback()
        raise HTTPException(400, "حداقل یک مدیر سیستم فعال باید وجود داشته باشد")
    db.commit()
    audit(db, me, "user_update", f"{u.username}: {data.model_dump(exclude={'password'}, exclude_none=True)}"
          + (" +password" if data.password else ""), request)
    return row(u)


@router.delete("/users/{uid}")
def delete_user(uid: int, request: Request, me: User = Depends(require("users.manage")),
                db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "کاربر یافت نشد")
    if u.id == me.id:
        raise HTTPException(400, "نمی‌توانید حساب خودتان را حذف کنید")
    name = u.username
    db.delete(u)
    db.flush()
    if _active_admins(db) == 0:
        db.rollback()
        raise HTTPException(400, "حداقل یک مدیر سیستم فعال باید وجود داشته باشد")
    db.commit()
    audit(db, me, "user_delete", name, request)
    return {"ok": True}


@router.get("/audit")
def audit_log(limit: int = 100, _: User = Depends(require("audit.view")), db: Session = Depends(get_db)):
    rows = db.query(Audit).order_by(Audit.id.desc()).limit(min(limit, 500)).all()
    return [{"id": a.id, "ts": a.ts.isoformat() + "Z", "username": a.username, "action": a.action,
             "detail": a.detail, "ip": a.ip} for a in rows]
