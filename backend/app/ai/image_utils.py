from __future__ import annotations
from typing import Any, Dict, List
import numpy as np
import cv2


def decode_upload_to_bgr(upload_file) -> np.ndarray:
    raw = upload_file.file.read()
    arr = np.frombuffer(raw, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Falha ao decodificar imagem.")
    return bgr


def encode_png_rgba(bgra: np.ndarray) -> bytes:
    rgba = cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA)
    ok, buf = cv2.imencode(".png", rgba)
    if not ok:
        raise RuntimeError("Falha ao codificar PNG.")
    return buf.tobytes()


def _laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _estimate_white_bg_ratio(bgr: np.ndarray, thr: int = 235) -> float:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    s = hsv[:, :, 1]
    mask = (v >= thr) & (s <= 35)
    return float(np.mean(mask))


def _edge_density(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 80, 180)
    return float(np.mean(edges > 0))


def validate_garment_photo(bgr: np.ndarray) -> Dict[str, Any]:
    h, w = bgr.shape[:2]
    reasons: List[str] = []
    tips: List[str] = []

    if min(h, w) < 480:
        reasons.append("LOW_RESOLUTION")
        tips.append("Aproxime a peça e use maior resolução.")

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    sharpness = _laplacian_variance(gray)
    if sharpness < 70:
        reasons.append("TOO_BLURRY")
        tips.append("Imagem desfocada. Apoie o celular e aumente a luz.")

    brightness = float(np.mean(gray))
    if brightness < 70:
        reasons.append("LOW_LIGHT")
        tips.append("Pouca luz. Faça a foto em ambiente mais iluminado.")

    white_ratio = _estimate_white_bg_ratio(bgr, thr=235)
    if white_ratio < 0.25:
        reasons.append("BUSY_BACKGROUND")
        tips.append("Fundo poluído. Prefira fundo liso e com contraste.")

    ed = _edge_density(gray)
    if ed > 0.18:
        reasons.append("TOO_MUCH_TEXTURE")
        tips.append("Fundo com muita textura. Use fundo simples.")

    score = 1.0
    if "LOW_RESOLUTION" in reasons: score -= 0.18
    if "TOO_BLURRY" in reasons: score -= 0.25
    if "LOW_LIGHT" in reasons: score -= 0.18
    if "BUSY_BACKGROUND" in reasons: score -= 0.22
    if "TOO_MUCH_TEXTURE" in reasons: score -= 0.12

    score = float(np.clip(score, 0.0, 1.0))
    ok = score >= 0.55

    return {
        "ok": ok,
        "score": round(score, 3),
        "reasons": reasons,
        "tips": tips[:4],
        "signals": {
            "resolution": [int(w), int(h)],
            "sharpness": round(float(sharpness), 2),
            "brightness": round(float(brightness), 2),
            "white_bg_ratio": round(float(white_ratio), 3),
            "edge_density": round(float(ed), 3),
        },
    }


def _decontaminate_border(bgra: np.ndarray) -> np.ndarray:
    b = bgra[:, :, 0].astype(np.float32)
    g = bgra[:, :, 1].astype(np.float32)
    r = bgra[:, :, 2].astype(np.float32)
    a = bgra[:, :, 3].astype(np.float32) / 255.0

    edge = (a > 0.02) & (a < 0.85)
    strength = np.zeros_like(a, dtype=np.float32)
    strength[edge] = (0.85 - a[edge]) / 0.83

    factor = 1.0 - 0.35 * strength
    b = b * factor
    g = g * factor
    r = r * factor

    out = bgra.copy()
    out[:, :, 0] = np.clip(b, 0, 255).astype(np.uint8)
    out[:, :, 1] = np.clip(g, 0, 255).astype(np.uint8)
    out[:, :, 2] = np.clip(r, 0, 255).astype(np.uint8)
    return out


def _remove_white_background_to_bgra(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]

    bg = (v >= 235) & (s <= 40)
    alpha = (~bg).astype(np.uint8) * 255
    alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=1.2, sigmaY=1.2)
    alpha = np.clip(alpha, 0, 255).astype(np.uint8)

    bgra = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = alpha
    return _decontaminate_border(bgra)


def _grabcut_cutout_to_bgra(bgr: np.ndarray) -> np.ndarray:
    h, w = bgr.shape[:2]
    margin_x = int(w * 0.08)
    margin_y = int(h * 0.08)
    rect = (margin_x, margin_y, w - 2 * margin_x, h - 2 * margin_y)

    mask = np.zeros((h, w), np.uint8)
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)

    cv2.grabCut(bgr, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT)
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")

    k = max(3, int(min(h, w) * 0.01) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel, iterations=1)

    fg = cv2.GaussianBlur(fg, (0, 0), sigmaX=2.0, sigmaY=2.0)
    fg = np.clip(fg, 0, 255).astype(np.uint8)

    bgra = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = fg
    return _decontaminate_border(bgra)


def garment_cutout_auto_bgra(bgr: np.ndarray) -> np.ndarray:
    white_ratio = _estimate_white_bg_ratio(bgr, thr=232)
    if white_ratio >= 0.55:
        return _remove_white_background_to_bgra(bgr)
    return _grabcut_cutout_to_bgra(bgr)


def overlay_bgra_on_bgr(base_bgr: np.ndarray, fg_bgra: np.ndarray, x: int, y: int) -> np.ndarray:
    out = base_bgr.copy()
    bh, bw = out.shape[:2]
    fh, fw = fg_bgra.shape[:2]

    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(bw, x + fw)
    y2 = min(bh, y + fh)
    if x1 >= x2 or y1 >= y2:
        return out

    roi = out[y1:y2, x1:x2]
    fg_roi = fg_bgra[(y1 - y):(y2 - y), (x1 - x):(x2 - x)]

    alpha = (fg_roi[:, :, 3:4].astype(np.float32) / 255.0)
    fg_rgb = fg_roi[:, :, :3].astype(np.float32)
    bg_rgb = roi.astype(np.float32)

    comp = fg_rgb * alpha + bg_rgb * (1.0 - alpha)
    out[y1:y2, x1:x2] = np.clip(comp, 0, 255).astype(np.uint8)
    return out
