from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import cv2
import mediapipe as mp


@dataclass
class TorsoAnchor:
    x: int
    y: int
    w: int
    h: int


def detect_torso_anchor_mediapipe(person_bgr, width_ratio: float = 0.62, height_ratio: float = 0.55) -> Optional[TorsoAnchor]:
    h, w = person_bgr.shape[:2]
    rgb = cv2.cvtColor(person_bgr, cv2.COLOR_BGR2RGB)

    pose = mp.solutions.pose.Pose(
        static_image_mode=True,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
    )

    res = pose.process(rgb)
    pose.close()

    if not res.pose_landmarks:
        return None

    lm = res.pose_landmarks.landmark

    # ombros
    l_sh = lm[mp.solutions.pose.PoseLandmark.LEFT_SHOULDER]
    r_sh = lm[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]

    if (l_sh.visibility < 0.4) or (r_sh.visibility < 0.4):
        return None

    lx, ly = int(l_sh.x * w), int(l_sh.y * h)
    rx, ry = int(r_sh.x * w), int(r_sh.y * h)

    shoulder_w = max(1, abs(rx - lx))
    cx = (lx + rx) // 2
    cy = (ly + ry) // 2

    target_w = int(shoulder_w / width_ratio)  # “abre” um pouco além dos ombros
    target_h = int(target_w * height_ratio)

    x = int(cx - target_w // 2)
    y = int(cy - int(target_h * 0.25))  # sobe um pouco para pegar gola

    # clamp na imagem
    x = max(0, min(w - 1, x))
    y = max(0, min(h - 1, y))
    if x + target_w > w:
        target_w = w - x
    if y + target_h > h:
        target_h = h - y

    if target_w <= 20 or target_h <= 20:
        return None

    return TorsoAnchor(x=x, y=y, w=target_w, h=target_h)
