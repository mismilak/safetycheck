"""Grab frames from a webcam / RTSP stream / video file for labeling.

    python training/collect_frames.py --source 0 --every 2 --count 300
    python training/collect_frames.py --source rtsp://user:pass@192.168.1.20/stream1 --every 5 --count 500
"""
import argparse
import time
from pathlib import Path

import cv2

ap = argparse.ArgumentParser()
ap.add_argument("--source", default="0")
ap.add_argument("--every", type=float, default=2.0, help="seconds between saved frames")
ap.add_argument("--count", type=int, default=300)
ap.add_argument("--out", default=str(Path(__file__).parent / "dataset" / "raw_images"))
a = ap.parse_args()

out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
cap = cv2.VideoCapture(int(a.source) if a.source.isdigit() else a.source)
if not cap.isOpened():
    raise SystemExit(f"cannot open source {a.source!r}")
saved, last = 0, 0.0
tag = time.strftime("%Y%m%d_%H%M%S")
print(f"saving up to {a.count} frames to {out} (Ctrl+C to stop)")
try:
    while saved < a.count:
        ok, frame = cap.read()
        if not ok:
            break
        if time.time() - last >= a.every:
            last = time.time()
            cv2.imwrite(str(out / f"{tag}_{saved:05d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            saved += 1
            print(f"\r{saved}/{a.count}", end="", flush=True)
except KeyboardInterrupt:
    pass
print(f"\ndone: {saved} frames")
