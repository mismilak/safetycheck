"""Split a labeled YOLO dataset into train/val and write dataset/data.yaml.

Input layout (what Label Studio / CVAT / Roboflow export in "YOLO" format):
    <src>/images/*.jpg   and   <src>/labels/*.txt     (same file stems)

    python training/prepare_dataset.py --src ~/Downloads/my_export --val 0.2

Images without a label file are skipped (label empty background images explicitly with an empty .txt).
"""
import argparse
import random
import shutil
from pathlib import Path

HERE = Path(__file__).parent
ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--dst", default=str(HERE / "dataset"))
ap.add_argument("--val", type=float, default=0.2)
ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()

src, dst = Path(a.src), Path(a.dst)
imgs = sorted(p for p in (src / "images").glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
pairs = [(i, src / "labels" / f"{i.stem}.txt") for i in imgs if (src / "labels" / f"{i.stem}.txt").exists()]
if not pairs:
    raise SystemExit("no (image, label) pairs found")
random.Random(a.seed).shuffle(pairs)
n_val = max(1, int(len(pairs) * a.val))
for split, items in (("val", pairs[:n_val]), ("train", pairs[n_val:])):
    for sub in ("images", "labels"):
        (dst / sub / split).mkdir(parents=True, exist_ok=True)
    for img, lab in items:
        shutil.copy(img, dst / "images" / split / img.name)
        shutil.copy(lab, dst / "labels" / split / lab.name)
yaml = (HERE / "data.yaml").read_text().replace("path: dataset", f"path: {dst.resolve()}")
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
