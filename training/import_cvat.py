"""Convert a CVAT "YOLO 1.1" export into the dataset layout used by prepare_dataset.py, mapping classes BY NAME.

CVAT numbers classes in the order of YOUR labels (obj.names), which is not the model's order. This script reads obj.names,
maps every name to the id used by the model you are fine-tuning, and rewrites the label files.

    CVAT: Tasks -> Actions -> Export task dataset -> format "YOLO 1.1" -> tick "Save images"

    python training/import_cvat.py --src job_4590054_annotations_yolo1.1.zip
    python training/prepare_dataset.py --src training/dataset/imported --names-from models/ppe.pt --group-by-source

Name your CVAT labels  Person, Hardhat, NO-Hardhat, Safety Vest, NO-Safety Vest  and they map automatically. Any other name needs
--map, e.g.  --map "uniform=Safety Vest" "work clothes=Safety Vest".
"""
import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.vision.types import canonical  # noqa: E402

HERE = Path(__file__).parent
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True, help="the exported .zip, or the folder you extracted it to")
ap.add_argument("--names-from", default=str(HERE.parent / "models" / "ppe.pt"), help="the model you will fine-tune")
ap.add_argument("--out", default=str(HERE / "dataset" / "imported"))
ap.add_argument("--name", default="cvat", help="file-name prefix (use a different one per CVAT task/video)")
ap.add_argument("--map", nargs="*", default=[], metavar="CVAT_NAME=MODEL_NAME", help='e.g. "uniform=Safety Vest"')
ap.add_argument("--images", help="folder with the original images, if the export does not contain them")
ap.add_argument("--block", type=int, default=30, help="consecutive frames per block; whole blocks go to train OR val")
a = ap.parse_args()

src = Path(a.src)
tmp = None
if src.suffix.lower() == ".zip":
    tmp = tempfile.mkdtemp(prefix="cvat_")
    with zipfile.ZipFile(src) as z:
        z.extractall(tmp)  # Python strips absolute paths / ".." from member names
    root = Path(tmp)
else:
    root = src
names_files = list(root.rglob("obj.names"))
if not names_files:
    sys.exit("obj.names not found - is this a CVAT 'YOLO 1.1' export?")
cvat_names = [ln.strip() for ln in names_files[0].read_text(encoding="utf-8").splitlines() if ln.strip()]

if not Path(a.names_from).exists():
    sys.exit(f"model not found: {a.names_from}\nPut your PPE model at models/ppe.pt (python tools/download_ppe_model.py) or pass the path explicitly.")
from ultralytics import YOLO  # noqa: E402

model_names = YOLO(a.names_from).names  # id -> name
by_name = {n.lower(): int(i) for i, n in model_names.items()}
by_canon = {}
for i, n in model_names.items():
    c = canonical(n)
    if c:
        by_canon.setdefault(c, int(i))
explicit = {}
for item in a.map:
    k, _, v = item.partition("=")
    if v.strip().lower() not in by_name:
        sys.exit(f"--map target {v!r} is not a class of {a.names_from}: {sorted(model_names.values())}")
    explicit[k.strip().lower()] = by_name[v.strip().lower()]

mapping = {}
print("class mapping (CVAT -> model):")
for i, n in enumerate(cvat_names):
    key = n.lower()
    mid = explicit.get(key) if key in explicit else by_canon.get(canonical(n) or "", by_name.get(key))
    mapping[i] = mid
    print(f"  {i} {n!r:24s} -> {('%d %s' % (mid, model_names[mid])) if mid is not None else 'IGNORED (no match; use --map)'}")

# find label files (YOLO txt) and images
images = {p.stem: p for p in root.rglob("*") if p.suffix.lower() in IMG_EXT}
if a.images:
    images.update({p.stem: p for p in Path(a.images).rglob("*") if p.suffix.lower() in IMG_EXT})


def is_label_file(p: Path) -> bool:
    lines = [ln for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    return all(len(ln.split()) == 5 and re.fullmatch(r"[\d.eE+\- ]+", ln) for ln in lines)  # empty file = background image


labels = sorted(p for p in root.rglob("*.txt") if p.stem in images and is_label_file(p))
if not images:
    sys.exit("The export contains no images. Export again with 'Save images' ticked, or pass --images <folder>.")
if not labels:
    sys.exit("No label files matched an image (same file name). Check the export / --images folder.")

out = Path(a.out)
for sub in ("images", "labels"):
    (out / sub).mkdir(parents=True, exist_ok=True)
counts, dropped = {}, {}
for n, lab in enumerate(labels):
    stem = f"{a.name}b{n // a.block:02d}_{n:05d}"  # "<source>_<frame>": the prefix is the group used for the train/val split
    lines = []
    for ln in lab.read_text().splitlines():
        if not ln.strip():
            continue
        cls, rest = ln.split(None, 1)
        mid = mapping.get(int(cls))
        if mid is None:
            dropped[cvat_names[int(cls)]] = dropped.get(cvat_names[int(cls)], 0) + 1
            continue
        counts[mid] = counts.get(mid, 0) + 1
        lines.append(f"{mid} {rest}")
    img = images[lab.stem]
    shutil.copy(img, out / "images" / f"{stem}{img.suffix.lower()}")
    (out / "labels" / f"{stem}.txt").write_text("\n".join(lines))
if tmp:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\nimported {len(labels)} frames -> {out}")
for mid, c in sorted(counts.items()):
    print(f"  {model_names[mid]:16s} {c}")
for n, c in dropped.items():
    print(f"  WARNING: {c} boxes of {n!r} dropped (unmapped)")
if by_canon["person"] not in counts:
    print("WARNING: no Person boxes. Unlabeled people are learned as BACKGROUND, which hurts. Label Person too, or "
          "pre-label with training/autolabel.py and only add what is missing.")
if by_canon["helmet"] not in counts and by_canon["no_helmet"] not in counts:
    print("NOTE: no helmet labels; the model may forget helmets while fine-tuning. Add some or mix in public data.")
