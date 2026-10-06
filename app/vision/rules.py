"""Tracking + PPE association + temporal smoothing + alarm decision. Pure logic, no I/O."""
from dataclasses import dataclass, field

from .types import (HELMET, NO_HELMET, NO_VEST, PERSON, VEST, AlarmEvent, Box, Capabilities, Det,
                    FrameResult, PersonView)

SEV_RANK = {"medium": 1, "high": 2}


def iou(a: Box, b: Box) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def inside_fraction(inner: Box, outer: Box) -> float:
    """Fraction of `inner` area that lies inside `outer`."""
    ix1, iy1, ix2, iy2 = max(inner[0], outer[0]), max(inner[1], outer[1]), min(inner[2], outer[2]), min(inner[3], outer[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return inter / area if area > 0 else 0.0


def _center(b: Box) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


@dataclass
class Track:
    id: int
    box: Box
    first_seen: float
    last_seen: float
    helmet_score: float | None = None  # EMA in [0,1]; 1 = wearing
    vest_score: float | None = None
    bad_key: str | None = None
    bad_since: float = 0.0
    last_alarm: float = -1e9
    last_alarm_sev: int = 0


class IouTracker:
    def __init__(self, iou_thr: float = 0.25, max_age: float = 1.5):
        self.iou_thr, self.max_age = iou_thr, max_age
        self.tracks: dict[int, Track] = {}
        self._next = 1

    def update(self, boxes: list[Box], now: float) -> list[Track]:
        pairs = sorted(((iou(t.box, b), tid, i) for tid, t in self.tracks.items() for i, b in enumerate(boxes)),
                       reverse=True)
        used_t, used_b, assigned = set(), set(), {}
        for score, tid, i in pairs:
            if score < self.iou_thr:
                break
            if tid in used_t or i in used_b:
                continue
            used_t.add(tid), used_b.add(i)
            assigned[i] = self.tracks[tid]
        out = []
        for i, b in enumerate(boxes):
            t = assigned.get(i)
            if t is None:
                t = Track(self._next, b, now, now)
                self._next += 1
                self.tracks[t.id] = t
            t.box, t.last_seen = b, now
            out.append(t)
        for tid in [k for k, t in self.tracks.items() if now - t.last_seen > self.max_age]:
            del self.tracks[tid]
        return out


def _ema(prev: float | None, obs: float, alpha: float = 0.4) -> float:
    return obs if prev is None else prev * (1 - alpha) + obs * alpha


def observe_ppe(person: Box, dets: list[Det], caps: Capabilities) -> tuple[float | None, float | None]:
    """Return per-frame evidence (1.0 wearing, 0.0 missing, None unknown) for helmet and vest."""
    px1, py1, px2, py2 = person
    ph, pw = py2 - py1, px2 - px1
    head = (px1 - 0.15 * pw, py1 - 0.15 * ph, px2 + 0.15 * pw, py1 + 0.40 * ph)
    best = {HELMET: 0.0, NO_HELMET: 0.0, VEST: 0.0, NO_VEST: 0.0}
    for d in dets:
        if d.cls == HELMET:
            cx, cy = _center(d.box)
            if head[0] <= cx <= head[2] and head[1] <= cy <= head[3]:
                best[HELMET] = max(best[HELMET], d.conf)
        elif d.cls == NO_HELMET:
            cx, cy = _center(d.box)
            if head[0] <= cx <= head[2] and head[1] <= cy <= head[3]:
                best[NO_HELMET] = max(best[NO_HELMET], d.conf)
        elif d.cls in (VEST, NO_VEST):
            if inside_fraction(d.box, person) >= 0.5:
                best[d.cls] = max(best[d.cls], d.conf)

    def decide(pos: float, neg: float, capable: bool) -> float | None:
        if not capable:
            return None
        if pos > 0 and pos >= neg:
            return 1.0
        return 0.0  # explicit negative, or absence of the positive class

    return (decide(best[HELMET], best[NO_HELMET], caps.helmet),
            decide(best[VEST], best[NO_VEST], caps.vest))


def dedupe_people(persons: list[Det], contain: float = 0.9) -> list[Det]:
    """Drop a person box that lies (>= `contain` of its area) inside a more confident one: detectors often emit an extra
    upper-body box for the same person whose IoU is too low for NMS to merge it, which would double-count and double-alarm."""
    kept: list[Det] = []
    for p in sorted(persons, key=lambda d: -d.conf):
        if all(inside_fraction(p.box, k.box) < contain for k in kept):
            kept.append(p)
    return kept


class ComplianceEngine:
    """One instance per camera."""

    def __init__(self):
        self.tracker = IouTracker()

    def process(self, dets: list[Det], frame_h: int, now: float, *, caps: Capabilities, require_helmet: bool,
                require_vest: bool, violation_seconds: float, cooldown_seconds: float,
                min_person_height: float = 0.0) -> FrameResult:
        persons = [d for d in dets if d.cls == PERSON and (d.box[3] - d.box[1]) >= min_person_height * frame_h]
        persons = dedupe_people(persons)
        tracks = self.tracker.update([p.box for p in persons], now)
        res = FrameResult()
        for t in tracks:
            h_obs, v_obs = observe_ppe(t.box, dets, caps)
            if h_obs is not None:
                t.helmet_score = _ema(t.helmet_score, h_obs)
            if v_obs is not None:
                t.vest_score = _ema(t.vest_score, v_obs)
            helmet = None if t.helmet_score is None else t.helmet_score >= 0.5
            vest = None if t.vest_score is None else t.vest_score >= 0.5

            required = []
            if require_helmet:
                required.append(("helmet", helmet))
            if require_vest:
                required.append(("vest", vest))
            known = [(n, ok) for n, ok in required if ok is not None]
            missing = [n for n, ok in known if not ok]
            if not known:
                status = "unknown"
            elif not missing:
                status = "safe"
            elif len(missing) == len(known):
                status = "unsafe"
            else:
                status = "partial"

            vsec = 0.0
            if missing:
                key = "no_both" if len(missing) == 2 else f"no_{missing[0]}"
                if key != t.bad_key:
                    t.bad_key, t.bad_since = key, now
                vsec = now - t.bad_since
                sev = "high" if status == "unsafe" else "medium"
                due = vsec >= violation_seconds
                allowed = (now - t.last_alarm >= cooldown_seconds) or SEV_RANK[sev] > t.last_alarm_sev
                if due and allowed:
                    t.last_alarm, t.last_alarm_sev = now, SEV_RANK[sev]
                    res.alarms.append(AlarmEvent(t.id, key, sev, vsec, t.box))
            else:
                t.bad_key = None
            res.persons.append(PersonView(t.id, t.box, helmet, vest, status, vsec))
        return res
