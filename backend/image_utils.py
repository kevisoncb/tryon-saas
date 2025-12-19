from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass
class TorsoAnchor:
    # posição do topo esquerdo onde a roupa deve ser aplicada
    x: int
    y: int
    # tamanho alvo da roupa
    w: int
    h: int


def is_background_white(
    image_bgr: np.ndarray,
    sample_border: int = 25,
    white_thresh: int = 235,
    min_white_ratio: float = 0.92,
) -> bool:
    if image_bgr is None or image_bgr.size == 0:
        return False

    h, w = image_bgr.shape[:2]
    b = max(5, min(sample_border, h // 10, w // 10))

    top = image_bgr[0:b, :, :]
    bottom = image_bgr[h - b : h, :, :]
    left = image_bgr[:, 0:b, :]
    right = image_bgr[:, w - b : w, :]

    border = np.concatenate(
        [
            top.reshape(-1, 3),
            bottom.reshape(-1, 3),
            left.reshape(-1, 3),
            right.reshape(-1, 3),
        ],
        axis=0,
    )

    white = (
        (border[:, 0] >= white_thresh)
        & (border[:, 1] >= white_thresh)
        & (border[:, 2] >= white_thresh)
    )
    return float(np.mean(white)) >= min_white_ratio


def remove_white_background_fast(
    garment_bgr: np.ndarray,
    white_thresh: int = 245,
    feather: int = 7,
    erode: int = 1,
    dilate: int = 2,
) -> np.ndarray:
    if garment_bgr is None or garment_bgr.size == 0:
        raise ValueError("garment_bgr is empty")

    garment = garment_bgr.astype(np.int16)
    white = np.array([white_point, white_point, white_point], dtype=np.int16)

    dist = np.linalg.norm(garment - white, axis=2).astype(np.float32)
    alpha = np.clip((dist - dist_thresh) * (255.0 / max(1.0, (255.0 - dist_thresh))), 0, 255).astype(np.uint8)

    if erode > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * erode + 1, 2 * erode + 1))
        alpha = cv2.erode(alpha, k, iterations=1)
    if dilate > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate + 1, 2 * dilate + 1))
        alpha = cv2.dilate(alpha, k, iterations=1)

    if feather and feather > 0:
        k = feather if feather % 2 == 1 else feather + 1
        alpha = cv2.GaussianBlur(alpha, (k, k), 0)

    bgra = cv2.cvtColor(garment_bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = alpha

    if dehalo_strength and dehalo_strength > 0:
        a = (alpha.astype(np.float32) / 255.0)
        factor = np.clip((1.0 - a) * float(dehalo_strength), 0.0, 1.0)

        rgb = bgra[:, :, 0:3].astype(np.float32)
        rgb = rgb * (1.0 - factor[:, :, None] * 0.12)
        bgra[:, :, 0:3] = np.clip(rgb, 0, 255).astype(np.uint8)

    return bgra


def _lm_xy(lm, w: int, h: int) -> Tuple[float, float]:
    return float(lm.x) * w, float(lm.y) * h


def detect_torso_anchor_mediapipe(
    person_bgr: np.ndarray,
    width_scale: float = 1.35,
    height_ratio: float = 1.40,
    y_offset_ratio: float = 0.18,
) -> Optional[TorsoAnchor]:
    """
    Calcula um anchor baseado em ombros e quadris:
    - largura alvo = largura_ombros * width_scale
    - altura alvo = largura alvo * height_ratio
    - y ancora próximo do ombro (com offset)
    """
    if person_bgr is None or person_bgr.size == 0:
        return None

    # Import interno para evitar travar import em ambientes ruins
    import mediapipe as mp

    h, w = person_bgr.shape[:2]
    rgb = cv2.cvtColor(person_bgr, cv2.COLOR_BGR2RGB)

    mp_pose = mp.solutions.pose
    with mp_pose.Pose(static_image_mode=True, model_complexity=1, enable_segmentation=False) as pose:
        res = pose.process(rgb)

    if not res.pose_landmarks:
        return None

    lm = res.pose_landmarks.landmark

    # Landmarks relevantes
    # ombros
    ls = lm[mp_pose.PoseLandmark.LEFT_SHOULDER]
    rs = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
    # quadris
    lh = lm[mp_pose.PoseLandmark.LEFT_HIP]
    rh = lm[mp_pose.PoseLandmark.RIGHT_HIP]

    lsx, lsy = _lm_xy(ls, w, h)
    rsx, rsy = _lm_xy(rs, w, h)
    lhx, lhy = _lm_xy(lh, w, h)
    rhx, rhy = _lm_xy(rh, w, h)

    shoulder_w = max(10.0, abs(rsx - lsx))
    center_x = (lsx + rsx) / 2.0

    # y_top baseado no ombro mais alto (menor y) com offset pra cima
    shoulder_top_y = min(lsy, rsy)
    y_top = shoulder_top_y - shoulder_w * y_offset_ratio

    target_w = int(shoulder_w * width_scale)
    target_h = int(target_w * height_ratio)

    x1 = int(center_x - target_w / 2)
    y1 = int(y_top)

    # Garantir que a roupa cubra pelo menos até a linha do quadril
    hip_y = max(lhy, rhy)
    min_h = int(max(target_h, (hip_y - y1) * 1.05))
    target_h = max(target_h, min_h)

    # Clamp
    x1 = max(0, min(x1, w - 2))
    y1 = max(0, min(y1, h - 2))

    # Ajustar se passar do frame
    if x1 + target_w > w:
        x1 = max(0, w - target_w)
    if y1 + target_h > h:
        target_h = max(10, h - y1)

    return TorsoAnchor(x=x1, y=y1, w=max(10, target_w), h=max(10, target_h))


def overlay_bgra_on_bgr(base_bgr: np.ndarray, overlay_bgra: np.ndarray, x: int, y: int) -> np.ndarray:
    out = base_bgr.copy()
    bh, bw = out.shape[:2]
    oh, ow = overlay_bgra.shape[:2]

    # área destino (clamp)
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(bw, x + ow)
    y2 = min(bh, y + oh)

    if x1 >= x2 or y1 >= y2:
        return out

    # área correspondente do overlay
    ox1 = x1 - x
    oy1 = y1 - y
    ox2 = ox1 + (x2 - x1)
    oy2 = oy1 + (y2 - y1)

    roi = out[y1:y2, x1:x2].astype(np.float32)
    ov = overlay_bgra[oy1:oy2, ox1:ox2].astype(np.float32)

    alpha = ov[:, :, 3:4] / 255.0
    ov_rgb = ov[:, :, 0:3]
    blended = roi * (1.0 - alpha) + ov_rgb * alpha

    out[y1:y2, x1:x2] = blended.astype(np.uint8)
    return out
