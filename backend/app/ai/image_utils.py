from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import mediapipe as mp


@dataclass
class AnchorBox:
    x: int
    y: int
    w: int
    h: int


def is_background_white_strict(bgr: np.ndarray, sample_border: int = 20) -> bool:
    """
    Checa se o fundo da imagem é "branco suficiente".
    Estratégia: amostrar bordas e medir quão perto está de branco.
    """
    h, w = bgr.shape[:2]
    b = sample_border

    top = bgr[:b, :, :]
    bottom = bgr[h - b :, :, :]
    left = bgr[:, :b, :]
    right = bgr[:, w - b :, :]

    samples = np.concatenate(
        [
            top.reshape(-1, 3),
            bottom.reshape(-1, 3),
            left.reshape(-1, 3),
            right.reshape(-1, 3),
        ],
        axis=0,
    )

    # branco: (255,255,255) em BGR também.
    mean = samples.mean(axis=0)
    # tolerância bem exigente
    return bool((mean > np.array([245, 245, 245])).all())


def remove_white_background_premium(bgr: np.ndarray) -> np.ndarray:
    """
    Remove fundo branco e retorna BGRA.
    Faz anti-halo + feather simples.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    # máscara do branco no HSV
    lower = np.array([0, 0, 200], dtype=np.uint8)
    upper = np.array([180, 50, 255], dtype=np.uint8)
    mask_white = cv2.inRange(hsv, lower, upper)

    # objeto = invert
    mask_obj = cv2.bitwise_not(mask_white)

    # limpeza
    kernel = np.ones((3, 3), np.uint8)
    mask_obj = cv2.morphologyEx(mask_obj, cv2.MORPH_OPEN, kernel, iterations=1)
    mask_obj = cv2.morphologyEx(mask_obj, cv2.MORPH_CLOSE, kernel, iterations=2)

    # feather
    mask_f = cv2.GaussianBlur(mask_obj, (0, 0), sigmaX=1.2, sigmaY=1.2)

    # monta BGRA
    b, g, r = cv2.split(bgr)
    a = mask_f
    bgra = cv2.merge([b, g, r, a])

    return bgra


def detect_torso_anchor_mediapipe(person_bgr: np.ndarray) -> Optional[AnchorBox]:
    """
    Detecta um retângulo aproximado na região do torso/ombros para ancorar a roupa.
    """
    mp_pose = mp.solutions.pose
    rgb = cv2.cvtColor(person_bgr, cv2.COLOR_BGR2RGB)

    with mp_pose.Pose(static_image_mode=True, model_complexity=1, enable_segmentation=False) as pose:
        res = pose.process(rgb)
        if not res.pose_landmarks:
            return None

        h, w = person_bgr.shape[:2]
        lm = res.pose_landmarks.landmark

        # ombros
        ls = lm[mp_pose.PoseLandmark.LEFT_SHOULDER]
        rs = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
        lh = lm[mp_pose.PoseLandmark.LEFT_HIP]
        rh = lm[mp_pose.PoseLandmark.RIGHT_HIP]

        xs = [ls.x, rs.x, lh.x, rh.x]
        ys = [ls.y, rs.y, lh.y, rh.y]

        min_x = int(max(0, min(xs) * w))
        max_x = int(min(w - 1, max(xs) * w))
        min_y = int(max(0, min(ys) * h))
        max_y = int(min(h - 1, max(ys) * h))

        box_w = max_x - min_x
        box_h = max_y - min_y

        # padding
        pad_x = int(box_w * 0.15)
        pad_y = int(box_h * 0.10)

        x = max(0, min_x - pad_x)
        y = max(0, min_y - pad_y)
        ww = min(w - x, box_w + 2 * pad_x)
        hh = min(h - y, box_h + 2 * pad_y)

        # mínimo razoável
        if ww < 50 or hh < 50:
            return None

        return AnchorBox(x=x, y=y, w=ww, h=hh)


def overlay_bgra_on_bgr(background_bgr: np.ndarray, fg_bgra: np.ndarray, x: int, y: int) -> np.ndarray:
    """
    Composita fg_bgra em background_bgr na posição (x,y).
    """
    out = background_bgr.copy()
    bh, bw = out.shape[:2]
    fh, fw = fg_bgra.shape[:2]

    x2 = min(bw, x + fw)
    y2 = min(bh, y + fh)

    if x >= bw or y >= bh or x2 <= x or y2 <= y:
        return out

    roi = out[y:y2, x:x2]
    fg = fg_bgra[0 : y2 - y, 0 : x2 - x]

    alpha = fg[:, :, 3].astype(np.float32) / 255.0
    alpha = alpha[:, :, None]

    fg_rgb = fg[:, :, :3].astype(np.float32)
    roi_f = roi.astype(np.float32)

    comp = fg_rgb * alpha + roi_f * (1.0 - alpha)
    out[y:y2, x:x2] = comp.astype(np.uint8)
    return out
