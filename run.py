"""Start SafetyCheck:  python run.py"""
import uvicorn

from app.config import config

if __name__ == "__main__":
    print(f"\n  SafetyCheck → http://localhost:{config.port}\n")
    uvicorn.run("app.main:asgi", host=config.host, port=config.port, log_level="info", ws_ping_interval=None)
