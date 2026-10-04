import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import VERSION, config
from .db import Base, SessionLocal, engine
from .hub import hub
from .models import Camera, User
from .routers import alarms, auth, cameras, reports, stats, stream, system, users
from .runtime import get_runtime
from .security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("safetycheck")
STATIC = Path(__file__).parent / "static"


def bootstrap() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(User).count() == 0:
            pw = config.admin_password or secrets.token_urlsafe(9)
            db.add(User(username=config.admin_username.lower(), full_name="مدیر سیستم", role="admin",
                        password_hash=hash_password(pw), must_change_password=not config.admin_password))
            if not config.admin_password:
                bar = "=" * 60
                print(f"\n{bar}\n  SafetyCheck: first-run admin account\n  username: {config.admin_username}\n"
                      f"  password: {pw}   (change it after first login)\n{bar}\n", flush=True)
        if db.query(Camera).count() == 0:
            demo_only = config.detector == "demo"
            db.add(Camera(name="وب‌کم لپ‌تاپ", location="محل نصب", source="0", enabled=not demo_only))
            db.add(Camera(name="دوربین نمایشی (دمو)", location="شبیه‌ساز", source="demo", enabled=demo_only))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    hub.bind(asyncio.get_running_loop())
    rt = get_runtime()
    rt.start()
    yield
    rt.stop()


app = FastAPI(title="SafetyCheck", version=VERSION, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # CSRF: state-changing API calls must carry a custom header (cross-site forms cannot set it)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/") \
            and request.headers.get("x-sc") != "1":
        return JSONResponse({"detail": "درخواست نامعتبر"}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    return resp


for r in (auth, users, cameras, alarms, stats, reports, system, stream):
    app.include_router(r.router)


class CachedStatic(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            if path.startswith(("vendor/", "fonts/", "icons/")):
                resp.headers["Cache-Control"] = "public, max-age=2592000, immutable"
            else:
                resp.headers["Cache-Control"] = "no-cache"  # revalidate via ETag
        return resp


app.mount("/static", CachedStatic(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def sw():
    return FileResponse(STATIC / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/offline.html", include_in_schema=False)
def offline():
    return FileResponse(STATIC / "offline.html")


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


# gzip for text assets/JSON, but never for the MJPEG stream or websockets
_inner = GZipMiddleware(app, minimum_size=700)


async def asgi(scope, receive, send):
    if scope["type"] == "http" and not scope["path"].startswith("/api/stream"):
        await _inner(scope, receive, send)
    else:
        await app(scope, receive, send)
