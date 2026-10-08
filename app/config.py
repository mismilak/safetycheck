from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
VERSION = "1.0.0"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SC_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    data_dir: Path = BASE_DIR / "data"
    models_dir: Path = BASE_DIR / "models"
    secret_key: str = ""
    token_minutes: int = 600
    cookie_secure: bool = False
    detector: str = "auto"  # auto | yolo | demo
    model_path: str = "ppe.pt"
    person_model: str = "yolo11n.pt"
    device: str = "cpu"
    imgsz: int = 640
    # FFmpeg options for rtsp:// sources: TCP avoids smeared/gray frames, nobuffer+low_delay avoid latency build-up.
    rtsp_options: str = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay"
    admin_username: str = "admin"
    admin_password: str = ""

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def feedback_dir(self) -> Path:
        return self.data_dir / "feedback"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'safetycheck.db'}"


config = Config()
