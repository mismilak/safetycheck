"""Download a ready-made PPE model (helmet / safety vest, with Person + NO-Hardhat + NO-Safety Vest classes).

    python tools/download_ppe_model.py            # saves models/ppe.pt (existing file is backed up as ppe.pt.bak)

Source: github.com/VoxDroid/Construction-Site-Safety-PPE-Detection (MIT code license), YOLOv8s trained 200 epochs on the
Roboflow "Construction Site Safety" dataset. The file is pinned to a commit and verified by SHA-256.
CHECK the dataset / model licensing yourself before commercial use. Accuracy on YOUR cameras must be verified (and
ideally improved with training/README.md).
"""
import argparse
import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

COMMIT = "9f4c9cf401806dcdd0e16fd7491f179f64e5b3a4"
URL = ("https://github.com/VoxDroid/Construction-Site-Safety-PPE-Detection/raw/" + COMMIT +
       "/Model-Training/Outputs/runs/detect/yolov8s_ppe_css_200_epochs/weights/best.pt")
SHA256 = "470cc1d2f39774ade966488719d20635da56431123a8b189ec87fec041f0bc47"

ap = argparse.ArgumentParser()
ap.add_argument("--dest", default=str(Path(__file__).resolve().parent.parent / "models" / "ppe.pt"))
a = ap.parse_args()
dest = Path(a.dest)
dest.parent.mkdir(parents=True, exist_ok=True)
tmp = dest.with_suffix(".download")
print("downloading", URL)
with urllib.request.urlopen(URL, timeout=120) as r, open(tmp, "wb") as f:
    shutil.copyfileobj(r, f)
digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
if digest != SHA256:
    tmp.unlink(missing_ok=True)
    sys.exit(f"SHA-256 mismatch ({digest}); file discarded")
if dest.exists():
    shutil.copy(dest, dest.with_suffix(".pt.bak"))
tmp.replace(dest)
print(f"saved {dest} ({dest.stat().st_size / 1e6:.1f} MB, sha256 verified). Restart SafetyCheck.")
