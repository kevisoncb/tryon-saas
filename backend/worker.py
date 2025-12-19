from __future__ import annotations

import time
import traceback
from pathlib import Path

import cv2
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from models import TryOnJob
from image_utils import (
    is_background_white,
    remove_white_background_premium,
    detect_torso_anchor_mediapipe,
    overlay_bgra_on_bgr,
)

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RESULTS_DIR = STORAGE_DIR / "results"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

POLL_SECONDS = 2.0
MAX_ATTEMPTS = 3


def _get_one_queued_job(db: Session) -> TryOnJob | None:
    row = db.execute(
        text(
            """
            SELECT id
            FROM tryon_jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )
    ).fetchone()

    if not row:
        return None

    job_id = row[0]
    return db.query(TryOnJob).filter(TryOnJob.id == job_id).first()


def _set_status(db: Session, job: TryOnJob, status: str, err: str | None = None, result_path: str | None = None):
    job.status = status

    if status == "processing":
        job.attempts = (job.attempts or 0) + 1
        job.error_message = None
        job.last_error = None

    if status == "done":
        job.result_image_path = result_path
        job.error_message = None
        job.last_error = None

    if status == "error":
        msg = (err or "Unknown error")[:2000]
        job.error_message = msg
        job.last_error = msg

    db.commit()
    db.refresh(job)


def _process_job(job: TryOnJob) -> str:
    person_path = Path(job.person_image_path)
    garment_path = Path(job.garment_image_path)

    if not person_path.exists():
        raise FileNotFoundError(f"Person image not found: {person_path}")
    if not garment_path.exists():
        raise FileNotFoundError(f"Garment image not found: {garment_path}")

    person_bgr = cv2.imread(str(person_path), cv2.IMREAD_COLOR)
    garment_bgr = cv2.imread(str(garment_path), cv2.IMREAD_COLOR)

    if person_bgr is None:
        raise ValueError("Failed to read person image (cv2.imread returned None)")
    if garment_bgr is None:
        raise ValueError("Failed to read garment image (cv2.imread returned None)")

    if not is_background_white(garment_bgr):
        raise ValueError("Garment background is not white enough. Upload the garment photo on a white background.")

    anchor = detect_torso_anchor_mediapipe(person_bgr)
    if anchor is None:
        raise ValueError("Could not detect pose/anchor. Try a full-body/clear photo.")

    garment_bgra = remove_white_background_premium(garment_bgr)

    garment_resized = cv2.resize(garment_bgra, (anchor.w, anchor.h), interpolation=cv2.INTER_AREA)
    out_bgr = overlay_bgra_on_bgr(person_bgr, garment_resized, anchor.x, anchor.y)

    out_path = RESULTS_DIR / f"{job.id}.png"
    ok = cv2.imwrite(str(out_path), out_bgr)
    if not ok:
        raise RuntimeError("Failed to write result image (cv2.imwrite returned False)")

    return str(out_path)


def main():
    print("Worker iniciado. Aguardando jobs queued... (CTRL+C para sair)")
    while True:
        db = SessionLocal()
        job = None
        try:
            db.begin()
            job = _get_one_queued_job(db)
            if not job:
                db.commit()
                time.sleep(POLL_SECONDS)
                continue

            if (job.attempts or 0) >= MAX_ATTEMPTS:
                _set_status(db, job, "error", err=f"Max attempts reached ({MAX_ATTEMPTS}).")
                time.sleep(0.2)
                continue

            _set_status(db, job, "processing")

            result_path = _process_job(job)
            _set_status(db, job, "done", result_path=result_path)
            print(f"[DONE] job={job.id} result={result_path}")

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            tb = traceback.format_exc()
            try:
                if job is not None:
                    _set_status(db, job, "error", err=err)
                    print(f"[ERROR] job={job.id} {err}")
                else:
                    print(f"[ERROR] {err}")
            except Exception:
                print("[ERROR] failed to persist error state")
            print(tb)

        finally:
            db.close()


if __name__ == "__main__":
    main()
