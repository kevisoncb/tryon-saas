from __future__ import annotations

import time
import traceback
from datetime import datetime
from pathlib import Path

import cv2
from sqlalchemy import text
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

POLL_SECONDS = 1.5
MAX_ATTEMPTS = 3


def _ts() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(job_id: str | None, msg: str):
    line = f"{_ts()} | {job_id or '-'} | {msg}"
    print(line)
    if job_id:
        try:
            (LOGS_DIR / f"{job_id}.log").open("a", encoding="utf-8").write(line + "\n")
        except Exception:
            # não derruba o worker por falha de log
            pass


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


def _read_bgr(path: Path) -> cv2.typing.MatLike:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Failed to read image with cv2.imread: {path}")
    return img


def _process_job(job: TryOnJob) -> str:
    person_path = Path(job.person_image_path)
    garment_path = Path(job.garment_image_path)

    if not person_path.exists():
        raise FileNotFoundError(f"Person image not found: {person_path}")
    if not garment_path.exists():
        raise FileNotFoundError(f"Garment image not found: {garment_path}")

    _log(str(job.id), f"Loading images person={person_path.name} garment={garment_path.name}")
    person_bgr = _read_bgr(person_path)
    garment_bgr = _read_bgr(garment_path)

    _log(str(job.id), "Validating garment background (strict white)")
    if not is_background_white_strict(garment_bgr):
        raise ValueError("Garment background is not white enough. Upload the garment photo on a clean white background.")

    _log(str(job.id), "Detecting pose anchor (shoulders)")
    anchor = detect_torso_anchor_mediapipe(person_bgr)
    if anchor is None:
        raise ValueError("Could not detect pose/anchor. Use a clear, full-body photo with visible shoulders/torso.")

    _log(str(job.id), f"Anchor: x={anchor.x} y={anchor.y} w={anchor.w} h={anchor.h}")

    _log(str(job.id), "Cutting out garment (premium alpha)")
    garment_bgra = remove_white_background_premium(garment_bgr)

    _log(str(job.id), "Resizing garment to anchor and compositing")
    garment_resized = cv2.resize(garment_bgra, (anchor.w, anchor.h), interpolation=cv2.INTER_AREA)
    out_bgr = overlay_bgra_on_bgr(person_bgr, garment_resized, anchor.x, anchor.y)

    out_path = RESULTS_DIR / f"{job.id}.png"
    ok = cv2.imwrite(str(out_path), out_bgr)
    if not ok:
        raise RuntimeError("Failed to write result image (cv2.imwrite returned False)")

    _log(str(job.id), f"Saved result: {out_path.name}")
    return str(out_path)


def main():
    _log(None, "Worker started. Waiting for queued jobs... (CTRL+C to stop)")
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

            job_id = str(job.id)

            if (job.attempts or 0) >= MAX_ATTEMPTS:
                _log(job_id, f"Max attempts reached ({MAX_ATTEMPTS}). Marking as error.")
                _set_status(db, job, "error", err=f"Max attempts reached ({MAX_ATTEMPTS}).")
                time.sleep(0.2)
                continue

            _log(job_id, f"Picked job (attempt={(job.attempts or 0) + 1}/{MAX_ATTEMPTS})")
            _set_status(db, job, "processing")

            result_path = _process_job(job)
            _set_status(db, job, "done", result_path=result_path)
            _log(job_id, "Job done")

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            tb = traceback.format_exc()

            try:
                if job is not None:
                    _log(str(job.id), f"Job error: {err}")
                    _set_status(db, job, "error", err=err)
                else:
                    _log(None, f"Worker error (no job): {err}")
            except Exception:
                _log(None, "Failed to persist error state in DB")

            # log stacktrace em arquivo quando houver job
            if job is not None:
                try:
                    (LOGS_DIR / f"{job.id}.log").open("a", encoding="utf-8").write(tb + "\n")
                except Exception:
                    pass

        finally:
            db.close()


if __name__ == "__main__":
    main()
