from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import cv2
from PIL import Image


@dataclass
class TorsoBox:
    x: int
    y: int
    w: int
    h: int


def _pil_to_bgr(img: Image.Image) -> np.ndarray:
    rgb = np.array(img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def remove_white_background_fast(input_path: Path, output_png_path: Path) -> None:
    """
    Remove fundo branco (ou quase branco) de uma imagem de roupa e salva PNG com alpha.
    Recomendado quando você orienta o usuário a enviar fundo branco.
    """
    img = Image.open(input_path).convert("RGBA")
    rgba = np.array(img)  # (H,W,4)
    rgb = rgba[..., :3].astype(np.uint8)

    # pixels "quase brancos" -> alpha 0
    # ajuste fino: quanto maior o threshold, mais agressivo (pode comer detalhes claros)
    threshold = 245
    white_mask = (rgb[..., 0] >= threshold) & (rgb[..., 1] >= threshold) & (rgb[..., 2] >= threshold)

    alpha = rgba[..., 3].copy()
    alpha[white_mask] = 0

    # suavizar borda (feather) para não ficar serrilhado
    alpha_blur = cv2.GaussianBlur(alpha, (0, 0), sigmaX=1.2, sigmaY=1.2)
    rgba[..., 3] = alpha_blur

    out = Image.fromarray(rgba, mode="RGBA")
    output_png_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(output_png_path, format="PNG")


def detect_torso_box_mediapipe(person_path: Path) -> Optional[TorsoBox]:
    """
    Detecta região do tronco usando MediaPipe Pose:
    - usa ombro esquerdo/direito e quadril esquerdo/direito (quando disponíveis)
    - retorna uma caixa aproximada do torso (x,y,w,h) em pixels
    """
    import mediapipe as mp  # lazy import

    img_pil = Image.open(person_path).convert("RGB")
    bgr = _pil_to_bgr(img_pil)
    h, w = bgr.shape[:2]

    mp_pose = mp.solutions.pose
    with mp_pose.Pose(static_image_mode=True, model_complexity=1, enable_segmentation=False) as pose:
        results = pose.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        if not results.pose_landmarks:
            return None

        lm = results.pose_landmarks.landmark

        # índices MediaPipe Pose
        L_SH = 11
        R_SH = 12
        L_HIP = 23
        R_HIP = 24

        def pt(i: int) -> Tuple[float, float, float]:
            return lm[i].x, lm[i].y, lm[i].visibility

        lshx, lshy, lv = pt(L_SH)
        rshx, rshy, rv = pt(R_SH)
        lhx, lhy, hv = pt(L_HIP)
        rhx, rhy, hv2 = pt(R_HIP)

        # precisa de landmarks minimamente visíveis
        if min(lv, rv, hv, hv2) < 0.4:
            return None

        # converter para pixels
        sh_left = (int(lshx * w), int(lshy * h))
        sh_right = (int(rshx * w), int(rshy * h))
        hip_left = (int(lhx * w), int(lhy * h))
        hip_right = (int(rhx * w), int(rhy * h))

        x1 = min(sh_left[0], sh_right[0], hip_left[0], hip_right[0])
        x2 = max(sh_left[0], sh_right[0], hip_left[0], hip_right[0])
        y1 = min(sh_left[1], sh_right[1])
        y2 = max(hip_left[1], hip_right[1])

        # margens (para pegar peito/abdômen com folga)
        pad_x = int((x2 - x1) * 0.15)
        pad_top = int((y2 - y1) * 0.10)
        pad_bottom = int((y2 - y1) * 0.05)

        x = max(0, x1 - pad_x)
        y = max(0, y1 - pad_top)
        x_end = min(w - 1, x2 + pad_x)
        y_end = min(h - 1, y2 + pad_bottom)

        return TorsoBox(x=x, y=y, w=(x_end - x), h=(y_end - y))
