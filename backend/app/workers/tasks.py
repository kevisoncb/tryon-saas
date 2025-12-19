from __future__ import annotations

import traceback
from pathlib import Path
from uuid import UUID

import cv2
from sqlalchemy.orm import Session

from app.core.logging import log_job
from app.core.paths import RESULTS_DIR
from app.infra.db.database import SessionLocal
from app.infra.db.models import TryOnJob
from app.ai.image_utils import (
    is_background_white_strict,
    remove_white_background_premium,
    detect_torso_anchor_mediapipe,
    overlay_bgra_on_bgr,
)


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

        log_job(job_id, "Loading images")
        person_bgr = _read_bgr(Path(job.person_image_path))
        garment_bgr = _read_bgr(Path(job.garment_image_path))

        log_job(job_id, "Validating white background")
        if not is_background_white_strict(garment_bgr):
            raise ValueError("Garment background is not white enough. Use a clean white background.")

        log_job(job_id, "Detecting torso anchor")
        anchor = detect_torso_anchor_mediapipe(person_bgr)
        if anchor is None:
            raise ValueError("Pose anchor not detected. Use a clear photo with visible shoulders/torso.")

        log_job(job_id, "Removing white background (premium)")
        garment_bgra = remove_white_background_premium(garment_bgr)

        log_job(job_id, "Compositing overlay")
        garment_resized = cv2.resize(garment_bgra, (anchor.w, anchor.h), interpolation=cv2.INTER_AREA)
        out_bgr = overlay_bgra_on_bgr(person_bgr, garment_resized, anchor.x, anchor.y)

        out_path = RESULTS_DIR / f"{job.id}.png"
        ok = cv2.imwrite(str(out_path), out_bgr)
        if not ok:
            raise RuntimeError("Failed to write output image")

        job.status = "done"
        job.result_image_path = str(out_path)
        job.error_message = None
        db.commit()

        log_job(job_id, f"Done: {out_path.name}")

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

        log_job(job_id, f"ERROR: {err}")
        try:
            # grava traceback no log do job
            from app.core.paths import LOGS_DIR

            (LOGS_DIR / f"{job_id}.log").open("a", encoding="utf-8").write(tb + "\n")
        except Exception:
            pass

    finally:
        db.close()
