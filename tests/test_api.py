import time

import pytest

from app.main import app
from tests.conftest import Client, H


@pytest.fixture(scope="module")
def admin(client):
    assert client.login().status_code == 200
    return client


def mk(admin, username, role, pw="Passw0rd1"):
    r = admin.post("/api/users", json={"username": username, "role": role, "password": pw, "full_name": username},
                   headers=H)
    assert r.status_code == 201, r.text


def as_user(username, pw="Passw0rd1"):
    c = Client(app)
    assert c.login(username, pw).status_code == 200
    return c


def test_unauthenticated_blocked(client):
    c = Client(app)
    assert c.get("/api/cameras").status_code == 401
    assert c.get("/api/alarms").status_code == 401
    assert c.get("/api/stream/1").status_code == 401
    assert c.get("/api/public").status_code == 200


def test_csrf_header_required(client):
    c = Client(app)
    assert c.post("/api/auth/login", json={"username": "admin", "password": "Admin1234"}).status_code == 403


def test_login_flow_and_lockout(admin):
    me = admin.get("/api/auth/me").json()
    assert me["role"] == "admin" and "users.manage" in me["permissions"]
    c = Client(app)
    for _ in range(5):
        assert c.login("admin", "wrong").status_code == 401
    assert c.login("admin", "Admin1234").status_code == 429


def test_rbac_matrix(admin):
    for name, role in [("viewer1", "viewer"), ("oper1", "operator"), ("mgr1", "manager")]:
        mk(admin, name, role)
    v, o, m = as_user("viewer1"), as_user("oper1"), as_user("mgr1")
    # viewer: read only
    assert v.get("/api/cameras").status_code == 200
    assert v.get("/api/stats").status_code == 200
    assert v.get("/api/users").status_code == 403
    assert v.get("/api/settings").status_code == 403
    assert v.post("/api/alarms/ack-all", headers=H).status_code == 403
    assert v.get("/api/reports/alarms.csv").status_code == 403
    # operator: can handle alarms, cannot manage cameras
    assert o.post("/api/alarms/ack-all", headers=H).status_code == 200
    assert o.post("/api/cameras", json={"name": "x", "source": "demo"}, headers=H).status_code == 403
    # manager: cameras + reports + settings view; not users / settings edit
    assert m.get("/api/reports/alarms.csv").status_code == 200
    assert m.get("/api/settings").status_code == 200
    assert m.put("/api/settings", json={"detect_fps": 5}, headers=H).status_code == 403
    assert m.get("/api/users").status_code == 403
    assert m.post("/api/cameras", json={"name": "rtsp cam", "source": "rtsp://u:p@10.0.0.5/s", "enabled": False},
                  headers=H).status_code == 201
    # credentials in rtsp URLs are masked for those who cannot manage cameras
    cams = v.get("/api/cameras").json()
    assert any("***@" in c["source"] and "u:p" not in c["source"] for c in cams)


def test_user_management_guards(admin):
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/users/{me['id']}", json={"is_active": False}, headers=H).status_code == 400
    assert admin.patch(f"/api/users/{me['id']}", json={"role": "viewer"}, headers=H).status_code == 400
    assert admin.delete(f"/api/users/{me['id']}", headers=H).status_code == 400
    assert admin.post("/api/users", json={"username": "weak", "role": "viewer", "password": "12345678"},
                      headers=H).status_code == 400
    assert admin.post("/api/users", json={"username": "viewer1", "role": "viewer", "password": "Passw0rd1"},
                      headers=H).status_code == 409
    # deactivated user loses access immediately
    users = {u["username"]: u for u in admin.get("/api/users").json()}
    v = as_user("viewer1")
    admin.patch(f"/api/users/{users['viewer1']['id']}", json={"is_active": False}, headers=H)
    assert v.get("/api/cameras").status_code == 401
    assert admin.get("/api/audit").json()


def test_password_change(admin):
    mk(admin, "pwuser", "viewer")
    c = as_user("pwuser")
    assert c.post("/api/auth/password", json={"current_password": "bad", "new_password": "Newpass99"}, headers=H).status_code == 400
    assert c.post("/api/auth/password", json={"current_password": "Passw0rd1", "new_password": "Newpass99"}, headers=H).status_code == 200
    assert Client(app).login("pwuser", "Newpass99").status_code == 200


def test_settings_secret_masking(admin):
    admin.put("/api/settings", json={"telegram_token": "123:abc", "detect_fps": 999}, headers=H)
    s = admin.get("/api/settings").json()
    assert s["telegram_token"].startswith("•") and s["detect_fps"] == 30
    admin.put("/api/settings", json={"telegram_token": s["telegram_token"]}, headers=H)  # masked value keeps secret
    from app.runtime import get_runtime
    assert get_runtime().settings.get("telegram_token") == "123:abc"


def test_camera_validation(admin):
    assert admin.post("/api/cameras", json={"name": "bad", "source": "file:///etc/passwd"}, headers=H).status_code == 400
    assert admin.post("/api/cameras", json={"name": "", "source": "demo"}, headers=H).status_code == 400


def test_demo_pipeline_end_to_end(admin):
    """Enable the demo camera, with a short violation threshold; expect live frames and alarms."""
    admin.put("/api/settings", json={"violation_seconds": 0.5, "cooldown_seconds": 5, "detect_fps": 15}, headers=H)
    cams = admin.get("/api/cameras").json()
    demo = next(c for c in cams if c["source"] == "demo")
    r = admin.put(f"/api/cameras/{demo['id']}", json={**demo, "enabled": True}, headers=H)
    assert r.status_code == 200
    deadline = time.time() + 20
    items = []
    while time.time() < deadline:
        items = admin.get("/api/alarms").json()["items"]
        if items:
            break
        time.sleep(0.5)
    assert items, "no alarms generated by demo scene"
    a = items[0]
    assert a["kind"] in ("no_helmet", "no_vest", "no_both")
    img = admin.get(f"/api/alarms/{a['id']}/image")
    assert img.status_code == 200 and img.content[:2] == b"\xff\xd8"
    assert admin.get(f"/api/alarms/{a['id']}/image?thumb=true").status_code == 200
    # (MJPEG streaming is verified against a real server by tests/e2e_browser.py; TestClient buffers endless bodies)
    # websocket requires auth and pushes live data
    with admin.websocket_connect("/ws") as ws:
        assert ws.receive_json()["t"] == "hello"
        msg = None
        for _ in range(40):
            msg = ws.receive_json()
            if msg["t"] == "live":
                break
        assert msg["t"] == "live" and msg["counts"]["total"] >= 1
    with pytest.raises(Exception):
        with Client(app).websocket_connect("/ws"):
            pass
    # handle + stats + reports
    assert admin.patch(f"/api/alarms/{a['id']}", json={"status": "false_positive", "note": "تست"}, headers=H).json()["status"] == "false_positive"
    st = admin.get("/api/stats?days=7&tz_offset=-210").json()
    assert st["summary"]["alarms"] >= 1 and len(st["hourly"]) == 24 and len(st["daily"]) == 7
    x = admin.get("/api/reports/alarms.xlsx")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    csv_ = admin.get("/api/reports/alarms.csv")
    assert "شناسه" in csv_.content.decode("utf-8-sig")
    assert admin.get("/api/system/status").json()["detector"]["mode"] == "demo"
