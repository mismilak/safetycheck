"""Export weights for faster CPU / GPU inference. The app loads the result via SC_MODEL_PATH.

    python training/export.py --format openvino        # Intel CPU: typically 2-3x faster than .pt
    python training/export.py --format onnx
    python training/export.py --format engine --device 0   # NVIDIA TensorRT
"""
import argparse
from pathlib import Path

from ultralytics import YOLO

ap = argparse.ArgumentParser()
ap.add_argument("--weights", default=str(Path(__file__).parent.parent / "models" / "ppe.pt"))
ap.add_argument("--format", default="openvino", choices=["openvino", "onnx", "engine"])
ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--half", action="store_true", help="FP16 (GPU only)")
ap.add_argument("--device", default="cpu")
a = ap.parse_args()
out = YOLO(a.weights).export(format=a.format, imgsz=a.imgsz, half=a.half, device=a.device)
print("exported:", out, "\nNow set SC_MODEL_PATH to its name (relative to models/) and restart.")
