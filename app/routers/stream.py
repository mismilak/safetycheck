import asyncio
import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..deps import _token_from, require, user_from_token
from ..hub import hub
from ..models import User
from ..runtime import get_runtime
from ..security import ROLE_PERMS

router = APIRouter(tags=["stream"])
BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "


@router.get("/api/stream/{cid}")
async def mjpeg(cid: int, _: User = Depends(require("live.view"))):
    w = get_runtime().workers.get(cid)
    if not w:
        raise HTTPException(404, "دوربین فعال نیست")

    async def gen():
        seq = -1
        try:
            while True:
                seq, jpeg = await asyncio.to_thread(w.wait_frame, seq, 2.0)
                if jpeg is None:
                    continue
                yield BOUNDARY + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


@router.websocket("/ws")
async def ws(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and urlparse(origin).netloc != websocket.headers.get("host"):
        await websocket.close(code=1008)
        return
    with SessionLocal() as db:
        user = user_from_token(db, _token_from(websocket))
        ok = bool(user and "live.view" in ROLE_PERMS.get(user.role, set()))
    if not ok:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    q = hub.subscribe()
    rt = get_runtime()
    await websocket.send_text(json.dumps({"t": "hello", "cams": {
        str(cid): {"online": w.online, "counts": w.counts, "persons": w.persons, "fps": round(w.fps, 1)}
        for cid, w in rt.workers.items()}}))

    async def reader():
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass

    rtask = asyncio.create_task(reader())
    try:
        while not rtask.done():
            try:
                msg = await asyncio.wait_for(q.get(), 25)
                await websocket.send_text(msg)
            except asyncio.TimeoutError:
                await websocket.send_text('{"t":"ping"}')
    except Exception:  # noqa: BLE001
        pass
    finally:
        rtask.cancel()
        hub.unsubscribe(q)
