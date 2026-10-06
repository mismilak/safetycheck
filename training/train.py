"""Fine-tune a YOLO model on your PPE dataset (transfer learning from COCO weights).

    python training/train.py --epochs 80 --model yolo11n.pt
    python training/train.py --epochs 100 --model yolo11s.pt --device 0 --install   # GPU + copy best.pt to models/ppe.pt
"""
import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

HERE = Path(__file__).parent
ap = argparse.ArgumentParser()
ap.add_argument("--data", default=str(HERE / "dataset" / "data.yaml"))
ap.add_argument("--model", default="yolo11n.pt", help="n = fastest/CPU-friendly, s/m = more accurate (GPU)")
ap.add_argument("--epochs", type=int, default=80)
ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--device", default="cpu", help="cpu | 0 (first GPU)")
ap.add_argument("--patience", type=int, default=20, help="early stop if val does not improve")
ap.add_argument("--freeze", type=int, default=0,
                help="freeze the first N layers (e.g. 10 = backbone). Use when fine-tuning an existing PPE model on a SMALL "
                     "dataset so it keeps what it already knows")
ap.add_argument("--lr0", type=float, default=0.01, help="initial learning rate (use 0.002 when fine-tuning a PPE model)")
ap.add_argument("--name", default="ppe")
ap.add_argument("--install", action="store_true", help="copy best.pt to models/ppe.pt when done")
a = ap.parse_args()

model = YOLO(a.model)
res = model.train(
    data=a.data, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device, patience=a.patience,
    freeze=a.freeze or None, lr0=a.lr0,
    project=str(HERE / "runs"), name=a.name, exist_ok=True,
    # augmentations that matter for CCTV-style scenes (lighting, scale, partial occlusion)
    hsv_h=0.015, hsv_s=0.6, hsv_v=0.4, degrees=5, translate=0.1, scale=0.5, fliplr=0.5, mosaic=1.0, close_mosaic=10,
)
best = Path(res.save_dir) / "weights" / "best.pt"
print("best weights:", best)
if a.install:
    dst = HERE.parent / "models" / "ppe.pt"
    dst.parent.mkdir(exist_ok=True)
    shutil.copy(best, dst)
    print("installed ->", dst, "(restart SafetyCheck to load it)")
