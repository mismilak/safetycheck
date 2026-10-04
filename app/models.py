from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    password_hash: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    location: Mapped[str] = mapped_column(String(128), default="")
    source: Mapped[str] = mapped_column(String(512))  # "0", rtsp://..., file path, demo
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    require_helmet: Mapped[bool] = mapped_column(Boolean, default=True)
    require_vest: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Alarm(Base):
    __tablename__ = "alarms"
    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), index=True)
    track_id: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(16))  # no_helmet | no_vest | no_both
    severity: Mapped[str] = mapped_column(String(8), default="medium")  # medium | high
    duration: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    image: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)  # new | ack | false_positive
    handled_by: Mapped[str] = mapped_column(String(64), default="")
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    camera: Mapped[Camera] = relationship()


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class HourStat(Base):
    __tablename__ = "hour_stats"
    __table_args__ = (UniqueConstraint("hour_ts", "camera_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    hour_ts: Mapped[int] = mapped_column(Integer, index=True)  # unix ts floored to the hour (UTC)
    camera_id: Mapped[int] = mapped_column(Integer)
    persons: Mapped[int] = mapped_column(Integer, default=0)  # sum of person observations (known status)
    safe: Mapped[int] = mapped_column(Integer, default=0)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(48))
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")


Index("ix_alarm_cam_time", Alarm.camera_id, Alarm.created_at)
