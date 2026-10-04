from dataclasses import dataclass, field

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 (pixels)

PERSON, HELMET, VEST, NO_HELMET, NO_VEST = "person", "helmet", "vest", "no_helmet", "no_vest"

_ALIASES = {
    PERSON: {"person", "worker", "people", "human"},
    HELMET: {"hardhat", "helmet", "safetyhelmet", "hardhats", "helmets"},
    VEST: {"safetyvest", "vest", "hivis", "highvis", "reflectivevest", "safetyvests"},
    NO_HELMET: {"nohardhat", "nohelmet", "withouthelmet", "nosafetyhelmet"},
    NO_VEST: {"nosafetyvest", "novest", "withoutvest", "noreflectivevest"},
}


def canonical(name: str) -> str | None:
    key = "".join(ch for ch in name.lower() if ch.isalnum())
    for canon, names in _ALIASES.items():
        if key in names:
            return canon
    return None


@dataclass
class Det:
    cls: str
    conf: float
    box: Box


@dataclass
class Capabilities:
    person: bool = True
    helmet: bool = False  # model can tell helmet / no_helmet
    vest: bool = False


@dataclass
class PersonView:
    id: int
    box: Box
    helmet: bool | None  # None = unknown (model cannot verify)
    vest: bool | None
    status: str  # safe | partial | unsafe | unknown
    violation_seconds: float = 0.0

    def to_json(self) -> dict:
        return {"id": self.id, "helmet": self.helmet, "vest": self.vest, "status": self.status,
                "vsec": round(self.violation_seconds, 1)}


@dataclass
class AlarmEvent:
    track_id: int
    kind: str  # no_helmet | no_vest | no_both
    severity: str  # medium | high
    duration: float
    box: Box


@dataclass
class FrameResult:
    persons: list[PersonView] = field(default_factory=list)
    alarms: list[AlarmEvent] = field(default_factory=list)
