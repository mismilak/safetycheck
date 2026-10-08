"""Find out WHERE the slowness is: camera/network/decoding, or the AI model.

    python tools/benchmark_camera.py --source rtsp://user:pass@192.168.1.20:554/stream1
    python tools/benchmark_camera.py --source 0 --no-model          # webcam, capture only

It measures, independently of the dashboard:
  1. capture   - open time, resolution, codec, and how many frames/s OpenCV can actually pull (no AI at all)
  2. inference - milliseconds per detection with your model on this machine
and prints a verdict. Compare "capture" with what VLC / the camera's own page shows: if VLC is smooth but capture is low,
the cause is the decoding (resolution/codec) or RTSP settings, not the network.
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.vision.sources import open_capture  # noqa: E402  (applies the same RTSP/FFmpeg options as the app)

ap = argparse.ArgumentParser()
ap.add_argument("--source", required=True, help="0 / rtsp://... / video file")
ap.add_argument("--seconds", type=float, default=10.0)
ap.add_argument("--model", default=str(Path(__file__).resolve().parent.parent / "models" / "ppe.pt"))
ap.add_argument("--no-model", action="store_true", help="skip the inference benchmark")
ap.add_argument("--device", default="cpu")
a = ap.parse_args()

print(f"== 1) CAPTURE: {a.source if not '@' in a.source else a.source.split('@')[-1]}")
t = time.time()
cap = open_capture(a.source)
if not cap.isOpened():
    sys.exit("cannot open the source (wrong URL/credentials, camera busy, or unsupported codec)")
ok, frame = cap.read()
t_first = time.time() - t
if not ok:
    sys.exit("opened, but no frame arrived")
h, w = frame.shape[:2]
fcc = int(cap.get(cv2.CAP_PROP_FOURCC))
codec = "".join(chr((fcc >> (8 * i)) & 0xFF) for i in range(4)).strip() or "?"
nominal = cap.get(cv2.CAP_PROP_FPS) or 0
print(f"   first frame after {t_first:.1f}s | resolution {w}x{h} | codec tag '{codec}' | camera reports {nominal:.0f} fps")

n, gaps, last, t0 = 0, [], time.time(), time.time()
good = frame  # last successfully read frame (used for the inference benchmark)
while time.time() - t0 < a.seconds:
    ok, frame = cap.read()
    now = time.time()
    if not ok:
        break
    good = frame
    gaps.append(now - last)
    last = now
    n += 1
cap.release()
fps = n / max(time.time() - t0, 1e-6)
if not gaps:
    gaps = [0.0]
stalls = sum(g > 0.3 for g in gaps)
print(f"   measured capture: {fps:.1f} fps | median frame gap {statistics.median(gaps) * 1000:.0f} ms | "
      f"worst gap {max(gaps) * 1000:.0f} ms | stalls >300 ms: {stalls}")

infer_ms = None
if not a.no_model:
    print(f"== 2) INFERENCE: {a.model}")
    from ultralytics import YOLO
    m = YOLO(a.model)
    small = cv2.resize(good, (960, int(h * 960 / w))) if w > 960 else good
    m.predict(small, imgsz=640, device=a.device, verbose=False)  # warm-up
    ts = []
    for _ in range(15):
        t = time.time()
        m.predict(small, imgsz=640, device=a.device, verbose=False)
        ts.append((time.time() - t) * 1000)
    infer_ms = statistics.mean(ts)
    print(f"   {infer_ms:.0f} ms per detection (p95 {sorted(ts)[int(len(ts) * .95) - 1]:.0f} ms) -> max {1000 / infer_ms:.1f} detections/s on '{a.device}'")

print("\n== VERDICT")
target = nominal if 5 < nominal < 61 else 15
if fps < 0.7 * target or stalls > 3:
    print(f"* CAPTURE is the bottleneck ({fps:.1f} fps pulled). Not the AI. Try, in this order:")
    if w >= 1920:
        print(f"  - use the camera's SUB-STREAM (e.g. 640x360 or 1280x720). {w}x{h} is expensive to decode on CPU")
    if codec.lower() in ("hevc", "hev1", "h265", "hvc1"):
        print("  - switch the stream to H.264: H.265/HEVC decoding on CPU is 2-3x heavier")
    print("  - lower the camera's frame rate / bitrate; check the Wi-Fi (use cable) and that nothing else pulls the same stream")
    print("  - compare with VLC: smooth in VLC but slow here = decoding cost, not the network")
else:
    print(f"* Capture is fine ({fps:.1f} fps, {stalls} stalls).")
if infer_ms is not None:
    if infer_ms > 250:
        print(f"* The AI model is slow here ({infer_ms:.0f} ms). The video itself stays smooth (decoupled), but boxes/alarms update "
              f"only {1000 / infer_ms:.1f}x per second. Use a smaller model (yolov8n/yolo11n), export to OpenVINO/ONNX, a GPU, "
              f"or lower 'detections per second' in Settings.")
    else:
        print(f"* The AI model is fast enough ({infer_ms:.0f} ms).")
