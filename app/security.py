import secrets
import time
from datetime import datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from .config import config

ALGO = "HS256"

# --- RBAC -----------------------------------------------------------------
ROLES = ["admin", "manager", "operator", "viewer"]
ROLE_LABELS = {"admin": "مدیر سیستم", "manager": "مدیر ایمنی", "operator": "اپراتور", "viewer": "بیننده"}

_VIEWER = {"live.view", "alarms.view", "stats.view"}
_OPERATOR = _VIEWER | {"alarms.handle"}
_MANAGER = _OPERATOR | {"reports.export", "cameras.manage", "settings.view"}
_ADMIN = _MANAGER | {"alarms.delete", "settings.edit", "users.manage", "audit.view"}
ROLE_PERMS: dict[str, set[str]] = {"viewer": _VIEWER, "operator": _OPERATOR, "manager": _MANAGER, "admin": _ADMIN}


def perms_of(role: str) -> list[str]:
    return sorted(ROLE_PERMS.get(role, set()))


# --- secrets / passwords ---------------------------------------------------
def _load_secret() -> str:
    if config.secret_key:
        return config.secret_key
    f = config.data_dir / "secret.key"
    if f.exists():
        return f.read_text().strip()
    key = secrets.token_urlsafe(48)
    f.write_text(key)
    try:
        f.chmod(0o600)
    except OSError:
        pass
    return key


SECRET = _load_secret()


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def check_password_strength(pw: str) -> str | None:
    if len(pw) < 8:
        return "رمز عبور باید حداقل ۸ کاراکتر باشد"
    if pw.isdigit() or pw.isalpha():
        return "رمز عبور باید ترکیبی از حرف و عدد باشد"
    return None


def make_token(user_id: int, role: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=config.token_minutes)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, SECRET, algorithm=ALGO)


def read_token(token: str) -> int | None:
    try:
        return int(jwt.decode(token, SECRET, algorithms=[ALGO])["sub"])
    except (JWTError, KeyError, ValueError):
        return None


# --- brute-force protection (in-memory) -------------------------------------
_fails: dict[str, list[float]] = {}
MAX_FAILS, WINDOW = 5, 300


def is_locked(key: str) -> bool:
    now = time.time()
    hits = [t for t in _fails.get(key, []) if now - t < WINDOW]
    _fails[key] = hits
    return len(hits) >= MAX_FAILS


def register_fail(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())


def clear_fails(key: str) -> None:
    _fails.pop(key, None)
