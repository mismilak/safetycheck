"""Generate a small synthetic YOLO dataset from the built-in demo scene.

Only for checking that the training scripts work end-to-end on your machine — NOT for a production model
(real accuracy requires labeled images from your own cameras, see training/README.md).

    python tools/make_synthetic_dataset.py --out /tmp/synth --n 80
"""
import argparse
from pathlib import Path

import cv2

from app.vision.sources import DEMO_H, DEMO_W, DemoSource

CLS = {"person": 0, "helmet": 1, "vest": 3}  # Person, Hardhat, Safety Vest (see training/data.yaml)

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--n", type=int, default=80)
a = ap.parse_args()
out = Path(a.out)
(out / "images").mkdir(parents=True, exist_ok=True)
(out / "labels").mkdir(parents=True, exist_ok=True)
src = DemoSource(seed=1)
for i in range(a.n):
    for _ in range(12):
        _, img, dets = src.read()
    cv2.imwrite(str(out / "images" / f"s{i:04d}.jpg"), img)
    lines = []
    for d in dets:
        x1, y1, x2, y2 = (max(0, d.box[0]), max(0, d.box[1]), min(DEMO_W, d.box[2]), min(DEMO_H, d.box[3]))
        lines.append(f"{CLS[d.cls]} {(x1 + x2) / 2 / DEMO_W:.6f} {(y1 + y2) / 2 / DEMO_H:.6f} {(x2 - x1) / DEMO_W:.6f} {(y2 - y1) / DEMO_H:.6f}")
    (out / "labels" / f"s{i:04d}.txt").write_text("\n".join(lines))
print("wrote", a.n, "samples to", out)
