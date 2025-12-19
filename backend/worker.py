from __future__ import annotations

import time
import traceback
from pathlib import Path
from uuid import UUID

import cv2
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from models import TryOnJob

from image_utils import (
    is_background_white,
    remove_white_background_fast,
    detect_torso_box_mediapipe,
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
    """
    Pega 1 job queued com lock (skip locked) para evitar concorrência.
    """
    # Usando SQL bruto para FOR UPDATE SKIP LOCKED (Postgres).
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
    job = db.query(TryOnJob).filter(TryOnJob.id == job_id).first()
    return job


def _set_processing(db: Session, job: TryOnJob):
    job.status = "processing"
    job.attempts = (job.attempts or 0) + 1
    job.last_error = None
    job.error_message = None
    job.processing_started_at = None  # opcional; se você usa, set aqui com datetime
    db.commit()
    db.refresh(job)


def _set_done(db: Session, job: TryOnJob, result_path: str):
    job.status = "done"
    job.result_image_path = result_path
    job.error_message = None
    job.last_error = None
    db.commit()


def _set_error(db: Session, job: TryOnJob, err: str):
    job.status = "error"
    job.error_message = err[:2000]
    job.last_error = err[:2000]
    db.commit()


def _process_job(job: TryOnJob) -> str:
    """
    Processa 1 job e retorna o caminho do resultado PNG.
    """
    person_path = Path(job.person_image_path)
    garment_path = Path(job.garment_image_path)

    if not person_path.exists():
        raise FileNotFoundError(f"Person image not found: {person_path}")
    if not garment_path.exists():
        raise FileNotFoundError(f"Garment image not found: {garment_path}")

    person_bgr = cv2.imread(str(person_path), cv2.IMREAD_COLOR)
    garment_bgr = cv2.imread(str(garment_path), cv2.IMREAD_COLOR)

    if person_bgr is None:
        raise ValueError("Failed to read person image")
    if garment_bgr is None:
        raise ValueError("Failed to read garment image")

    # 1) Validação: fundo branco recomendado
    if not is_background_white(garment_bgr):
        raise ValueError(
            "Garment background is not white enough. Please upload the garment photo on a white background."
        )

    # 2) Detect torso box no person
    box = detect_torso_box_mediapipe(person_bgr)
    if box is None:
        raise ValueError("Could not detect torso/pose on person image. Try a full-body/clear photo.")

    # 3) Remove fundo e gera BGRA
    garment_bgra = remove_white_background_fast(garment_bgr)

    # 4) Resize garment para caber no torso
    target_w = box.w
    target_h = box.h
    garment_resized = cv2.resize(garment_bgra, (target_w, target_h), interpolation=cv2.INTER_AREA)

    # 5) Overlay no person
    out_bgr = overlay_bgra_on_bgr(person_bgr, garment_resized, box.x1, box.y1)

    # 6) Salvar resultado
    out_path = RESULTS_DIR / f"{job.id}.png"
    ok = cv2.imwrite(str(out_path), out_bgr)
    if not ok:
        raise RuntimeError("Failed to write result image")

    return str(out_path)


def main():
    print("Worker iniciado. Aguardando jobs queued... (CTRL+C para sair)")
    while True:
        db = SessionLocal()
        try:
            db.begin()
            job = _get_one_queued_job(db)
            if not job:
                db.commit()
                time.sleep(POLL_SECONDS)
                continue

            # Se excedeu tentativas, marca erro definitivo
            if (job.attempts or 0) >= MAX_ATTEMPTS:
                _set_error(db, job, f"Max attempts reached ({MAX_ATTEMPTS}).")
                time.sleep(0.2)
                continue

            _set_processing(db, job)

            # Processamento pesado fora do lock
            result_path = _process_job(job)

            # Reabrir sessão para salvar resultado (ou reuse db, ok)
            _set_done(db, job, result_path)
            print(f"[DONE] job={job.id} result={result_path}")

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            tb = traceback.format_exc()
            try:
                # tenta marcar erro no job se existir
                if "job" in locals() and isinstance(locals()["job"], TryOnJob) and locals()["job"] is not None:
                    _set_error(db, locals()["job"], err)
                    print(f"[ERROR] job={locals()['job'].id} {err}")
                else:
                    print(f"[ERROR] {err}")
            except Exception:
                print("[ERROR] failed to persist error state")
            # Log detalhado no console (útil em dev)
            print(tb)

        finally:
            db.close()


if __name__ == "__main__":
    main()
