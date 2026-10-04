from app.vision.rules import ComplianceEngine, IouTracker, observe_ppe
from app.vision.types import Capabilities, Det

CAPS = Capabilities(helmet=True, vest=True)
KW = dict(caps=CAPS, require_helmet=True, require_vest=True, violation_seconds=3, cooldown_seconds=60)
PERSON = Det("person", 0.9, (100, 100, 200, 400))
HELMET = Det("helmet", 0.8, (125, 95, 175, 140))
VEST = Det("vest", 0.8, (110, 180, 190, 300))


def run(engine, dets, t0, secs, step=0.25, **kw):
    out, t = [], t0
    while t <= t0 + secs:
        out.append(engine.process(dets, 480, t, **{**KW, **kw}))
        t += step
    return out


def test_tracker_keeps_id():
    tr = IouTracker()
    a = tr.update([(0, 0, 100, 200)], 0)[0].id
    b = tr.update([(5, 5, 105, 205)], 0.1)[0].id
    c = tr.update([(500, 0, 600, 200)], 0.2)[0].id
    assert a == b and c != a


def test_association():
    assert observe_ppe(PERSON.box, [PERSON, HELMET, VEST], CAPS) == (1.0, 1.0)
    assert observe_ppe(PERSON.box, [PERSON], CAPS) == (0.0, 0.0)
    # helmet far from the head (e.g. held in hand / on a different person) does not count
    far = Det("helmet", 0.9, (125, 300, 175, 340))
    assert observe_ppe(PERSON.box, [PERSON, far], CAPS)[0] == 0.0
    # explicit negative class wins over absence
    assert observe_ppe(PERSON.box, [PERSON, Det("no_helmet", 0.7, (125, 100, 175, 140))], CAPS)[0] == 0.0
    # unknown when model has no helmet capability
    assert observe_ppe(PERSON.box, [PERSON], Capabilities())[0] is None


def test_safe_person_no_alarm():
    res = run(ComplianceEngine(), [PERSON, HELMET, VEST], 0, 10)
    assert all(not r.alarms for r in res)
    assert res[-1].persons[0].status == "safe"


def test_alarm_after_duration_and_cooldown():
    e = ComplianceEngine()
    res = run(e, [PERSON, VEST], 0, 10)  # missing helmet
    fired = [(i, a) for i, r in enumerate(res) for a in r.alarms]
    assert len(fired) == 1
    assert fired[0][1].kind == "no_helmet" and fired[0][1].severity == "medium"
    assert 3 <= fired[0][1].duration < 3.5
    assert res[-1].persons[0].status == "partial"


def test_escalation_to_both_fires_again():
    e = ComplianceEngine()
    run(e, [PERSON, VEST], 0, 5)
    res = run(e, [PERSON], 5.25, 6)
    kinds = [a.kind for r in res for a in r.alarms]
    assert kinds == ["no_both"]


def test_brief_dropout_does_not_alarm():
    e = ComplianceEngine()
    run(e, [PERSON, HELMET, VEST], 0, 5)
    res = run(e, [PERSON, VEST], 5.25, 0.75)  # helmet missed for ~1 s only
    assert all(not r.alarms for r in res)


def test_requirements_respected():
    res = run(ComplianceEngine(), [PERSON, VEST], 0, 8, require_helmet=False)
    assert all(not r.alarms for r in res)
    assert res[-1].persons[0].status == "safe"


def test_unknown_when_model_blind():
    res = run(ComplianceEngine(), [PERSON], 0, 8, caps=Capabilities())
    assert all(not r.alarms for r in res) and res[-1].persons[0].status == "unknown"


def test_small_far_person_ignored():
    tiny = Det("person", 0.9, (10, 10, 30, 40))
    res = run(ComplianceEngine(), [tiny], 0, 8, min_person_height=0.12)
    assert res[-1].persons == []


def test_class_name_mapping_for_common_ppe_datasets():
    from app.vision.types import canonical
    expect = {"Hardhat": "helmet", "NO-Hardhat": "no_helmet", "Safety Vest": "vest", "NO-Safety Vest": "no_vest",
              "Person": "person", "helmet": "helmet", "Helmet": "helmet", "vest": "vest", "no_helmet": "no_helmet",
              "worker": "person"}
    for name, canon in expect.items():
        assert canonical(name) == canon, name
    for other in ("Safety Cone", "Mask", "NO-Mask", "machinery", "vehicle"):
        assert canonical(other) is None


def test_composite_detector_adds_people_to_ppe_only_model():
    from app.vision.detector import CompositeDetector

    class Fake:
        def __init__(self, dets, caps, label):
            self._d, self.caps, self.label = dets, caps, label
        def detect(self, frame, conf, hint=None):
            return list(self._d)
        def info(self):
            return {"mode": "ppe", "model": self.label, "caps": vars(self.caps), "classes": []}

    ppe = Fake([HELMET, VEST], Capabilities(person=False, helmet=True, vest=True), "ppe.pt")
    people = Fake([PERSON, Det("person", 0.8, (300, 100, 400, 400)), Det("helmet", 0.9, (0, 0, 5, 5))],
                  Capabilities(), "yolo11n.pt")
    comp = CompositeDetector(ppe, people)
    dets = comp.detect(None, 0.4)
    assert sorted(d.cls for d in dets) == ["helmet", "person", "person", "vest"]  # people's stray helmet dropped
    assert comp.caps.person and comp.caps.helmet and comp.caps.vest
    assert "ppe.pt" in comp.info()["model"] and "yolo11n.pt" in comp.info()["model"]
    res = ComplianceEngine().process(dets, 480, 0.0, **KW)
    states = {p.status for p in res.persons}
    assert states == {"safe", "unsafe"}  # person 1 wears both, person 2 wears nothing
