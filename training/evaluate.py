"""Evaluate weights on the validation split: per-class precision / recall / mAP.

    python training/evaluate.py --weights models/ppe.pt
"""
import argparse
from pathlib import Path

from ultralytics import YOLO

HERE = Path(__file__).parent
ap = argparse.ArgumentParser()
ap.add_argument("--weights", default=str(HERE.parent / "models" / "ppe.pt"))
ap.add_argument("--data", default=str(HERE / "dataset" / "data.yaml"))
ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--device", default="cpu")
a = ap.parse_args()

m = YOLO(a.weights)
r = m.val(data=a.data, imgsz=a.imgsz, device=a.device, project=str(HERE / "runs"), name="eval", exist_ok=True)
print(f"\n{'class':18s}{'P':>8s}{'R':>8s}{'mAP50':>8s}")
present = [int(c) for c in r.box.ap_class_index]  # metrics exist only for classes that have val instances
for idx, ci in enumerate(present):
    p, rec, m50, _ = r.box.class_result(idx)
    flag = "  <-- weak" if m50 < 0.75 else ""
    print(f"{r.names[ci]:18s}{p:8.2f}{rec:8.2f}{m50:8.2f}{flag}")
for ci, name in r.names.items():
    if ci not in present:
        print(f"{name:18s}   (no instances in the validation set - add labeled examples)")
print(f"\nall classes: mAP50={r.box.map50:.3f}  mAP50-95={r.box.map:.3f}")
print("confusion matrix + PR curves:", Path(r.save_dir))
