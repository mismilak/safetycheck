from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import config
from ..db import get_db
from ..deps import COOKIE, audit, current_user
from ..models import User
from ..security import (ROLE_LABELS, check_password_strength, clear_fails, hash_password, is_locked, make_token,
                        perms_of, register_fail, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_DUMMY = hash_password("dummy-password-for-timing")


def user_json(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
            "role_label": ROLE_LABELS.get(u.role, u.role), "permissions": perms_of(u.role),
            "must_change_password": u.must_change_password}


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}|{data.username.lower()}"
    if is_locked(key):
        raise HTTPException(429, "تلاش‌های ناموفق زیاد بود. چند دقیقه بعد دوباره تلاش کنید")
    user = db.query(User).filter(User.username == data.username.strip().lower()).one_or_none()
    ok = verify_password(data.password, user.password_hash if user else _DUMMY)
    if not (user and ok and user.is_active):
        register_fail(key)
        audit(db, data.username[:64], "login_failed", "", request)
        raise HTTPException(401, "نام کاربری یا رمز عبور اشتباه است")
    clear_fails(key)
    user.last_login = datetime.utcnow()
    db.commit()
    audit(db, user, "login", "", request)
    response.set_cookie(COOKIE, make_token(user.id, user.role), httponly=True, samesite="lax",
                        secure=config.cookie_secure, max_age=config.token_minutes * 60, path="/")
    return user_json(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_json(user)


@router.post("/password")
def change_password(data: PasswordIn, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "رمز فعلی اشتباه است")
    if data.new_password == data.current_password:
        raise HTTPException(400, "رمز جدید باید با رمز فعلی متفاوت باشد")
    if (err := check_password_strength(data.new_password)):
        raise HTTPException(400, err)
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    db.commit()
    audit(db, user, "password_change", "", request)
    return user_json(user)
