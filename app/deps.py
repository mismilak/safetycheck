from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import Audit, User
from .security import ROLE_PERMS, read_token

COOKIE = "sc_token"


def _token_from(request) -> str | None:
    tok = request.cookies.get(COOKIE)
    if tok:
        return tok
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else None


def user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    uid = read_token(token)
    user = db.get(User, uid) if uid else None
    return user if user and user.is_active else None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_token(db, _token_from(request))
    if not user:
        raise HTTPException(401, "نیاز به ورود به سیستم")
    return user


def require(perm: str):
    def dep(user: User = Depends(current_user)) -> User:
        if perm not in ROLE_PERMS.get(user.role, set()):
            raise HTTPException(403, "شما دسترسی لازم برای این عملیات را ندارید")
        return user
    return dep


def audit(db: Session, user: User | str | None, action: str, detail: str = "", request: Request | None = None) -> None:
    name = user if isinstance(user, str) else (user.username if user else "")
    db.add(Audit(username=name, action=action, detail=detail[:500],
                 ip=(request.client.host if request and request.client else "")))
    db.commit()
