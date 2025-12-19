from __future__ import annotations

import traceback
from pathlib import Path
from uuid import UUID

import cv2
from sqlalchemy.orm import Session

from config import LOGS_DIR, RESULTS_DIR
from database import SessionLocal
from models import TryOnJob
from image_utils import (
    is_background_white_strict,
    remove_white_background_premium,
    detect_torso_anchor_mediapipe,
    overlay_bgra_on_bgr,
)


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


def process_tryon_job(job_id: str) -> None:
    db: Session = SessionLocal()
    try:
        jid = UUID(job_id)
        job = db.query(TryOnJob).filter(TryOnJob.id == jid).first()
        if not job:
            return

        job.status = "processing"
        job.error_message = None
        db.commit()

        _log(job_id, "Loading images")
        person_bgr = _read_bgr(Path(job.person_image_path))
        garment_bgr = _read_bgr(Path(job.garment_image_path))

        _log(job_id, "Validating white background")
        if not is_background_white_strict(garment_bgr):
            raise ValueError("Garment background is not white enough. Use clean white background.")

        _log(job_id, "Detecting anchor")
        anchor = detect_torso_anchor_mediapipe(person_bgr)
        if anchor is None:
            raise ValueError("Pose anchor not detected. Ensure shoulders/torso are visible.")

        _log(job_id, "Cutting garment")
        garment_bgra = remove_white_background_premium(garment_bgr)

        _log(job_id, "Compositing")
        garment_resized = cv2.resize(garment_bgra, (anchor.w, anchor.h), interpolation=cv2.INTER_AREA)
        out_bgr = overlay_bgra_on_bgr(person_bgr, garment_resized, anchor.x, anchor.y)

        out_path = RESULTS_DIR / f"{job.id}.png"
        ok = cv2.imwrite(str(out_path), out_bgr)
        if not ok:
            raise RuntimeError("Failed to write output")

        job.status = "done"
        job.result_image_path = str(out_path)
        job.error_message = None
        db.commit()

        _log(job_id, f"Done: {out_path.name}")

    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        tb = traceback.format_exc()
        try:
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
