from __future__ import annotations

import traceback
from pathlib import Path
from uuid import UUID

import cv2
import redis
from sqlalchemy.orm import Session

from database import SessionLocal
from models import TryOnJob
from image_utils import (
    is_background_white_strict,
    remove_white_background_premium,
    detect_torso_anchor_mediapipe,
    overlay_bgra_on_bgr,
)

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RESULTS_DIR = STORAGE_DIR / "results"
LOGS_DIR = STORAGE_DIR / "logs"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _log(job_id: str, msg: str):
    line = f"{job_id} | {msg}"
    print(line)
    try:
        (LOGS_DIR / f"{job_id}.log").open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass


def _read_bgr(path: Path):
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Failed to read image: {path}")
    return img


def _process(job: TryOnJob) -> str:
    job_id = str(job.id)

    person_path = Path(job.person_image_path)
    garment_path = Path(job.garment_image_path)

    if not person_path.exists():
        raise FileNotFoundError(f"Person image not found: {person_path}")
    if not garment_path.exists():
        raise FileNotFoundError(f"Garment image not found: {garment_path}")

    _log(job_id, f"Loading images: {person_path.name} / {garment_path.name}")
    person_bgr = _read_bgr(person_path)
    garment_bgr = _read_bgr(garment_path)

    _log(job_id, "Validating garment background (strict white)")
    if not is_background_white_strict(garment_bgr):
        raise ValueError("Garment background is not white enough. Use a clean white background.")

    _log(job_id, "Detecting shoulder anchor (mediapipe)")
    anchor = detect_torso_anchor_mediapipe(person_bgr)
    if anchor is None:
        raise ValueError("Pose anchor not found. Use a clear photo with visible shoulders/torso.")

    _log(job_id, f"Anchor: x={anchor.x} y={anchor.y} w={anchor.w} h={anchor.h}")

    _log(job_id, "Cutting garment (premium alpha)")
    garment_bgra = remove_white_background_premium(garment_bgr)

    garment_resized = cv2.resize(garment_bgra, (anchor.w, anchor.h), interpolation=cv2.INTER_AREA)
    out_bgr = overlay_bgra_on_bgr(person_bgr, garment_resized, anchor.x, anchor.y)

    out_path = RESULTS_DIR / f"{job.id}.png"
    ok = cv2.imwrite(str(out_path), out_bgr)
    if not ok:
        raise RuntimeError("Failed to write output image")

    _log(job_id, f"Saved result: {out_path.name}")
    return str(out_path)


def process_tryon_job(job_id: str) -> None:
    """
    Função chamada pelo RQ Worker.
    job_id vem como string UUID.
    """
    db: Session = SessionLocal()
    try:
        jid = UUID(job_id)
        job = db.query(TryOnJob).filter(TryOnJob.id == jid).first()
        if not job:
            return

        job.status = "processing"
        job.error_message = None
        db.commit()

        result_path = _process(job)

        job.status = "done"
        job.result_image_path = result_path
        job.error_message = None
        db.commit()

    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        tb = traceback.format_exc()
        try:
            # tenta registrar no job
            job = db.query(TryOnJob).filter(TryOnJob.id == UUID(job_id)).first()
            if job:
                job.status = "error"
                job.error_message = err[:2000]
                db.commit()
        except Exception:
            pass

        try:
            (LOGS_DIR / f"{job_id}.log").open("a", encoding="utf-8").write(tb + "\n")
        except Exception:
            pass
    finally:
        db.close()
