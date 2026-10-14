"""Split a labeled YOLO dataset into train/val and write dataset/data.yaml.

Input layout (what Label Studio / CVAT / Roboflow export in "YOLO" format):
    <src>/images/*.jpg   and   <src>/labels/*.txt     (same file stems)

    python training/prepare_dataset.py --src ~/Downloads/my_export --val 0.2

Images without a label file are skipped (label empty background images explicitly with an empty .txt).
"""
import argparse
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _paths import resolve  # noqa: E402
ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--dst", default=str(HERE / "dataset"))
ap.add_argument("--val", type=float, default=0.2)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--names-from", help="weights file whose class names/ids to use (needed when fine-tuning that model, "
                "e.g. models/ppe.pt, so the head keeps its trained weights)")
ap.add_argument("--group-by-source", action="store_true",
                help="frames named <source>_<n>.jpg (e.g. from autolabel.py) stay together in train OR val; "
                     "avoids near-identical video frames leaking into validation")
a = ap.parse_args()

src, dst = resolve(a.src), Path(a.dst)
imgs = sorted(p for p in (src / "images").glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
pairs = [(i, src / "labels" / f"{i.stem}.txt") for i in imgs if (src / "labels" / f"{i.stem}.txt").exists()]
if not pairs:
    n_img = len(imgs)
    n_lab = len(list((src / "labels").glob("*.txt"))) if (src / "labels").exists() else 0
    raise SystemExit(
        f"no (image, label) pairs found in {src.resolve()}\n"
        f"  looked for {src / 'images'} ({'exists' if (src / 'images').exists() else 'MISSING'}, {n_img} images) and "
        f"{src / 'labels'} ({n_lab} label files) with matching file names.\n"
        "  - did the previous step (import_cvat.py / autolabel.py) finish with 'imported/saved N frames'?\n"
        "  - run commands from the project root, or give an absolute --src path.")
rnd = random.Random(a.seed)
if a.group_by_source:
    groups: dict[str, list] = {}
    for pr in pairs:
        groups.setdefault(pr[0].stem.rsplit("_", 1)[0], []).append(pr)
    keys = sorted(groups)
    rnd.shuffle(keys)
    target = max(1, round(a.val * len(pairs)))
    val_pairs: list = []
    for k in keys[:-1]:  # always leave at least one source for training
        if len(val_pairs) < target:
            val_pairs += groups[k]
    if not val_pairs:  # a single source: it must serve as both, so validation numbers will be optimistic
        print("WARNING: only one source group; validation reuses training frames (numbers will be optimistic)")
        val_pairs = list(groups[keys[0]])
    train_pairs = [pr for pr in pairs if pr not in val_pairs] or list(val_pairs)
    n_val = len(val_pairs)
    pairs = val_pairs + train_pairs
else:
    rnd.shuffle(pairs)
    n_val = max(1, int(len(pairs) * a.val))
for split, items in (("val", pairs[:n_val]), ("train", pairs[n_val:])):
    for sub in ("images", "labels"):
        (dst / sub / split).mkdir(parents=True, exist_ok=True)
    for img, lab in items:
        shutil.copy(img, dst / "images" / split / img.name)
        shutil.copy(lab, dst / "labels" / split / lab.name)
yaml = (HERE / "data.yaml").read_text().replace("path: dataset", f"path: {dst.resolve()}")
if a.names_from:
    from ultralytics import YOLO
    nm = YOLO(str(resolve(a.names_from))).names
    yaml = yaml.split("names:")[0] + "names:\n" + "".join(f"  {k}: {v}\n" for k, v in nm.items())
(dst / "data.yaml").write_text(yaml)

# sanity report: instances per class
names = {}
for line in yaml.splitlines():
    s = line.strip()
    if s[:1].isdigit() and ":" in s:
        k, v = s.split(":", 1)
        names[int(k)] = v.strip()
counts = {k: 0 for k in names}
for _, lab in pairs:
    for ln in lab.read_text().splitlines():
        if ln.strip():
            c = int(ln.split()[0])
            counts[c] = counts.get(c, 0) + 1
print(f"train={len(pairs) - n_val} val={n_val}  ->  {dst / 'data.yaml'}")
for k, v in sorted(counts.items()):
    flag = "   <-- too few (aim for 300+ per class)" if v < 100 else ""
    print(f"  {k} {names.get(k, '?'):16s} {v}{flag}")
