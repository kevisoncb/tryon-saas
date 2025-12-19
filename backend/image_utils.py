from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass
class TorsoBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def clamp(self, w: int, h: int) -> "TorsoBox":
        x1 = max(0, min(self.x1, w - 1))
        y1 = max(0, min(self.y1, h - 1))
        x2 = max(0, min(self.x2, w - 1))
        y2 = max(0, min(self.y2, h - 1))
        if x2 <= x1:
            x2 = min(w - 1, x1 + 1)
        if y2 <= y1:
            y2 = min(h - 1, y1 + 1)
        return TorsoBox(x1, y1, x2, y2)

    @property
    def w(self) -> int:
        return max(1, self.x2 - self.x1)

    @property
    def h(self) -> int:
        return max(1, self.y2 - self.y1)


def is_background_white(
    image_bgr: np.ndarray,
    sample_border: int = 25,
    white_thresh: int = 235,
    min_white_ratio: float = 0.92,
) -> bool:
    """
    Verifica se o fundo é predominantemente branco analisando apenas as bordas da imagem.
    Ideal para roupas fotografadas com fundo branco.

    - sample_border: espessura (px) da borda analisada
    - white_thresh: pixel considerado branco se B,G,R >= white_thresh
    - min_white_ratio: % mínimo de pixels brancos nas bordas
    """
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
    ratio = float(np.mean(white))
    return ratio >= min_white_ratio


def remove_white_background_fast(
    garment_bgr: np.ndarray,
    white_thresh: int = 245,
    feather: int = 7,
    erode: int = 1,
    dilate: int = 2,
) -> np.ndarray:
    """
    Remove fundo branco (rápido) gerando BGRA com alpha.
    - white_thresh: quão branco precisa ser pra virar transparente
    - feather: suaviza borda (blur no alpha)
    - erode/dilate: ajusta borda (anti-halo e consistência)
    """
    if garment_bgr is None or garment_bgr.size == 0:
        raise ValueError("garment_bgr is empty")

    b, g, r = cv2.split(garment_bgr)

    # Quanto mais branco (perto de 255), mais transparente
    white_mask = (b >= white_thresh) & (g >= white_thresh) & (r >= white_thresh)
    alpha = np.where(white_mask, 0, 255).astype(np.uint8)

    # Morphology para borda ficar melhor
    if erode > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * erode + 1, 2 * erode + 1))
        alpha = cv2.erode(alpha, k, iterations=1)
    if dilate > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate + 1, 2 * dilate + 1))
        alpha = cv2.dilate(alpha, k, iterations=1)

    # Feather (suaviza)
    if feather and feather > 0:
        k = feather if feather % 2 == 1 else feather + 1
        alpha = cv2.GaussianBlur(alpha, (k, k), 0)

    bgra = cv2.cvtColor(garment_bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = alpha
    return bgra


def detect_torso_box_mediapipe(
    person_bgr: np.ndarray,
    expand_x: float = 0.20,
    expand_y: float = 0.30,
) -> Optional[TorsoBox]:
    """
    Detecta um retângulo aproximado do torso usando MediaPipe Pose.
    Retorna TorsoBox ou None se falhar.
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

    xs = np.array([ls.x, rs.x, lh.x, rh.x]) * w
    ys = np.array([ls.y, rs.y, lh.y, rh.y]) * h

    x1, x2 = float(xs.min()), float(xs.max())
    y1, y2 = float(ys.min()), float(ys.max())

    # Expande um pouco para "pegar" camiseta/roupa
    bw = x2 - x1
    bh = y2 - y1

    x1 -= bw * expand_x
    x2 += bw * expand_x
    y1 -= bh * expand_y * 0.6
    y2 += bh * expand_y

    box = TorsoBox(int(x1), int(y1), int(x2), int(y2)).clamp(w, h)
    return box


def overlay_bgra_on_bgr(
    base_bgr: np.ndarray,
    overlay_bgra: np.ndarray,
    x: int,
    y: int,
) -> np.ndarray:
    """
    Sobrepõe overlay BGRA (com alpha) em base BGR na posição (x,y).
    Retorna uma cópia do base com overlay aplicado.
    """
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
