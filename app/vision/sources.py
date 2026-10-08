import math
import os
import random
import re
import time

import cv2
import numpy as np

from ..config import config
from .types import Det

DEMO_W, DEMO_H = 960, 540


def parse_source(src: str):
    s = src.strip()
    return int(s) if s.isdigit() else s


def open_capture(src: str) -> cv2.VideoCapture:
    s = parse_source(src)
    if isinstance(s, str) and re.match(r"^rtsps?://", s, re.I):
        # read by OpenCV's FFmpeg backend when the capture is opened; a value already set by the user wins
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", config.rtsp_options)
    cap = cv2.VideoCapture(s, cv2.CAP_ANY)
    if isinstance(s, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


class DemoSource:
    """Synthetic factory-floor scene with workers walking; PPE toggles over time so alarms occur."""

    def __init__(self, seed: int | None = None):
        rnd = random.Random(seed)
        self.rnd = rnd
        self.t0 = time.monotonic()
        self.workers = []
        specs = [(True, True), (False, True), (True, False), (False, False)]
        for i, (h, v) in enumerate(specs):
            self.workers.append({
                "x": rnd.uniform(80, DEMO_W - 160), "speed": rnd.choice([-1, 1]) * rnd.uniform(18, 34),
                "base_y": 250 + i * 55, "h": h, "v": v, "next_toggle": rnd.uniform(20, 40),
                "shirt": rnd.choice([(150, 90, 40), (90, 90, 150), (80, 130, 90)]),
            })
        self.bg = self._background()

    @staticmethod
    def _background():
        img = np.zeros((DEMO_H, DEMO_W, 3), np.uint8)
        for y in range(DEMO_H):
            v = int(70 + 60 * y / DEMO_H)
            img[y, :] = (v, v + 3, v + 8)
        cv2.rectangle(img, (0, 0), (DEMO_W, 150), (60, 52, 46), -1)
        for x in range(0, DEMO_W, 120):
            cv2.line(img, (x, 0), (x, 150), (80, 70, 62), 2)
        cv2.line(img, (0, 150), (DEMO_W, 150), (35, 140, 235), 4)
        for x in range(-40, DEMO_W, 90):
            cv2.line(img, (x, DEMO_H), (x + 160, 170), (95, 100, 108), 1)
        return img

    def read(self):
        now = time.monotonic() - self.t0
        img = self.bg.copy()
        dets: list[Det] = []
        for w in self.workers:
            w["x"] += w["speed"] * 0.06
            if w["x"] < 40 or w["x"] > DEMO_W - 140:
                w["speed"] *= -1
            if now > w["next_toggle"]:
                if self.rnd.random() < 0.5:
                    w["h"] = not w["h"]
                else:
                    w["v"] = not w["v"]
                w["next_toggle"] = now + self.rnd.uniform(25, 50)
            scale = 0.8 + (w["base_y"] - 250) / 500
            bob = math.sin(now * 5 + w["base_y"]) * 3
            x, by = int(w["x"]), int(w["base_y"] + bob)
            bw, bh = int(60 * scale), int(200 * scale)
            top = by - bh
            # legs, torso, head, helmet, vest
            cv2.rectangle(img, (x + int(bw * .2), by - int(bh * .38)), (x + int(bw * .8), by), (60, 50, 45), -1)
            torso_y1, torso_y2 = top + int(bh * .2), top + int(bh * .62)
            cv2.rectangle(img, (x, torso_y1), (x + bw, torso_y2), w["shirt"], -1)
            hr = int(bw * .3)
            hc = (x + bw // 2, top + hr + 2)
            cv2.circle(img, hc, hr, (140, 175, 215), -1)
            if w["h"]:
                cv2.ellipse(img, hc, (hr + 3, hr + 2), 0, 180, 360, (30, 210, 250), -1)
                cv2.rectangle(img, (hc[0] - hr - 5, hc[1] - 2), (hc[0] + hr + 5, hc[1] + 3), (30, 190, 230), -1)
            if w["v"]:
                cv2.rectangle(img, (x + 4, torso_y1), (x + bw - 4, torso_y2), (20, 120, 250), -1)
                cv2.rectangle(img, (x + 4, torso_y1 + int(bh * .12)), (x + bw - 4, torso_y1 + int(bh * .15)),
                              (210, 235, 240), -1)
            j = lambda: self.rnd.uniform(-2, 2)  # noqa: E731
            if self.rnd.random() > 0.03:  # occasional missed detection
                dets.append(Det("person", 0.9, (x + j(), top + j(), x + bw + j(), by + j())))
                if w["h"]:
                    dets.append(Det("helmet", 0.85, (hc[0] - hr - 5 + j(), hc[1] - hr - 3 + j(), hc[0] + hr + 5 + j(), hc[1] + 3 + j())))
                if w["v"]:
                    dets.append(Det("vest", 0.85, (x + 4 + j(), torso_y1 + j(), x + bw - 4 + j(), torso_y2 + j())))
        noise = np.random.randint(0, 6, img.shape, dtype=np.uint8)
        img = cv2.add(img, noise)
        return True, img, dets
