"""Auto-label frames so you can teach the model what YOUR work uniform looks like - without drawing a single box.

Idea: public PPE models learn "Safety Vest" = hi-vis vest, so a navy work jacket is called "NO-Safety Vest".
Record a short video (or photos) where EVERYONE visible wears the work uniform, and another where NOBODY does:

    python training/autolabel.py --source uniform.mp4  --uniform yes --every 6
    python training/autolabel.py --source civilian.mp4 --uniform no  --every 6
    python training/autolabel.py --source photos/      --uniform yes

For every frame the existing model (models/ppe.pt) supplies Person / Hardhat / NO-Hardhat boxes; the "Safety Vest" (yes) or
"NO-Safety Vest" (no) box is derived from the upper-body region below each head. Output (YOLO format) goes to
training/dataset/autolabeled/{images,labels,preview}. LOOK AT preview/ before training: wrong labels teach wrong things.

Then:
    python training/prepare_dataset.py --src training/dataset/autolabeled --names-from models/ppe.pt --group-by-source
    python training/train.py --model models/ppe.pt --freeze 10 --lr0 0.002 --epochs 40 --batch 8
"""
import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.vision.rules import dedupe_people  # noqa: E402
from app.vision.types import Det, canonical  # noqa: E402

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _paths import resolve  # noqa: E402
ap = argparse.ArgumentParser()
ap.add_argument("--source", required=True, help="video file, webcam index, RTSP url, or a folder of images")
ap.add_argument("--uniform", required=True, choices=["yes", "no"], help="does EVERY person in this source wear the work uniform?")
ap.add_argument("--model", default=str(HERE.parent / "models" / "ppe.pt"))
ap.add_argument("--out", default=str(HERE / "dataset" / "autolabeled"))
ap.add_argument("--name", help="prefix for file names (default: source name). Frames of one source stay together in train/val")
ap.add_argument("--every", type=int, default=5, help="keep every Nth video frame")
ap.add_argument("--max-frames", type=int, default=200)
ap.add_argument("--conf", type=float, default=0.5, help="minimum model confidence for Person/Hardhat boxes")
ap.add_argument("--min-height", type=float, default=0.25, help="ignore persons shorter than this fraction of the frame")
ap.add_argument("--torso", type=float, nargs=2, default=(0.18, 0.62), metavar=("TOP", "BOTTOM"),
                help="fallback torso band (fractions of person height) used only when no head/helmet is detected")
ap.add_argument("--device", default="cpu")
a = ap.parse_args()

a.model = str(resolve(a.model))
if not Path(a.model).exists():
    sys.exit(f"model not found: {a.model}\nPut your PPE model at models/ppe.pt (python tools/download_ppe_model.py) or pass the path explicitly.")
from ultralytics import YOLO  # noqa: E402

model = YOLO(a.model)
ids = {}  # canonical class -> model class id (so fine-tuning continues from the same head)
for i, n in model.names.items():
    c = canonical(n)
    if c:
        ids.setdefault(c, int(i))
need = ["person", "helmet", "no_helmet", "vest", "no_vest"]
miss = [n for n in need if n not in ids]
if miss:
    sys.exit(f"model {a.model} has no class for: {miss}. Use a PPE model with Person/Hardhat/NO-Hardhat/Safety Vest/NO-Safety Vest.")
vest_cls = ids["vest"] if a.uniform == "yes" else ids["no_vest"]

src = resolve(a.source)
if src.is_dir():
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"})

    def frames():
        for p in files:
            im = cv2.imread(str(p))
            if im is not None:
                yield p.stem, im
    name = a.name or src.name
else:
    cap = cv2.VideoCapture(int(a.source) if a.source.isdigit() else str(src))
    if not cap.isOpened():
        sys.exit(f"cannot open {a.source!r}")

    def frames():
        n = 0
        while True:
            ok, im = cap.read()
            if not ok:
                return
            if n % a.every == 0:
                yield f"{n:05d}", im
            n += 1
    name = a.name or ("webcam" if a.source.isdigit() else Path(a.source).stem)

out = Path(a.out)
for sub in ("images", "labels", "preview"):
    (out / sub).mkdir(parents=True, exist_ok=True)


def torso_box(person, head, torso_band):
    """Region that is certainly 'clothes on the upper body'. Anchored on the head when one is visible (anatomy is constant
    while framing is not: a webcam shows only the upper body, so fractions of the person box are unreliable):
    shoulders start ~0.6 helmet-widths below the helmet, the torso is ~2 helmet-widths tall and ~1.9 wide."""
    x1, y1, x2, y2 = person
    if head is not None:
        hx1, hy1, hx2, hy2 = head
        hw, cx = hx2 - hx1, (hx1 + hx2) / 2
        top = hy2 + 0.6 * hw
        half = min(0.95 * hw, 0.45 * (x2 - x1))
        return (cx - half, top, cx + half, min(top + 2.0 * hw, y2))
    pw, ph = x2 - x1, y2 - y1
    return (x1 + 0.12 * pw, y1 + torso_band[0] * ph, x2 - 0.12 * pw, y1 + torso_band[1] * ph)


def yolo_line(cls: int, box, w: int, h: int) -> str:
    x1, y1, x2, y2 = max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])
    return f"{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}"


kept = persons_total = 0
for tag, im in frames():
    if kept >= a.max_frames:
        break
    h, w = im.shape[:2]
    if max(h, w) > 1280:  # keep files small; training resizes to 640 anyway
        f = 1280 / max(h, w)
        im = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        h, w = im.shape[:2]
    r = model.predict(im, conf=a.conf, imgsz=640, device=a.device, verbose=False)[0]
    dets = [Det(canonical(model.names[int(c)]) or "", float(cf), tuple(b)) for c, cf, b in
            zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist())]
    people = dedupe_people([d for d in dets if d.cls == "person" and (d.box[3] - d.box[1]) >= a.min_height * h])
    if not people:
        continue
    lines, vis = [], im.copy()
    for p in people:
        x1, y1, x2, y2 = p.box
        pw, ph = x2 - x1, y2 - y1
        head = (x1 - 0.15 * pw, y1 - 0.15 * ph, x2 + 0.15 * pw, y1 + 0.40 * ph)
        heads = [d for d in dets if d.cls in ("helmet", "no_helmet")
                 and head[0] <= (d.box[0] + d.box[2]) / 2 <= head[2] and head[1] <= (d.box[1] + d.box[3]) / 2 <= head[3]]
        ref = max(heads, key=lambda d: d.conf).box if heads else None
        torso = torso_box(p.box, ref, a.torso)
        lines += [yolo_line(ids["person"], p.box, w, h), yolo_line(vest_cls, torso, w, h)]
        cv2.rectangle(vis, tuple(map(int, p.box[:2])), tuple(map(int, p.box[2:])), (80, 200, 80), 3)
        cv2.rectangle(vis, tuple(map(int, torso[:2])), tuple(map(int, torso[2:])), (0, 140, 255) if a.uniform == "yes" else (60, 60, 230), 3)
        for d in heads:
            lines.append(yolo_line(ids[d.cls], d.box, w, h))
            cv2.rectangle(vis, tuple(map(int, d.box[:2])), tuple(map(int, d.box[2:])), (255, 200, 60) if d.cls == "helmet" else (60, 60, 230), 3)
    stem = f"{name}_{tag}"
    cv2.imwrite(str(out / "images" / f"{stem}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 92])
    (out / "labels" / f"{stem}.txt").write_text("\n".join(lines))
    if kept < 12:
        cv2.imwrite(str(out / "preview" / f"{stem}.jpg"), cv2.resize(vis, None, fx=640 / max(h, w), fy=640 / max(h, w)))
    kept += 1
    persons_total += len(people)
    print(f"\r{kept} frames, {persons_total} persons", end="", flush=True)

print(f"\nsaved {kept} labeled frames ({persons_total} persons) -> {out}")
if kept == 0:
    sys.exit("no people found: check the source, or lower --conf / --min-height")
print(f"CHECK the first frames in {out / 'preview'}: green = person, orange/red = torso (vest class), blue = helmet.")
if kept < 100:
    print("NOTE: <100 frames. Use different people, rooms, distances, lighting and angles (front/side/back); 200+ frames per case is a good start.")
