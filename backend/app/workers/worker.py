from __future__ import annotations

import time
import traceback
from pathlib import Path
from uuid import UUID

import cv2
from sqlalchemy import select

from settings import RESULTS_DIR
from app.core.logging import job_log
from app.infra.db.database import SessionLocal
from app.infra.db.models import TryOnJob
from app.infra.db.crud import get_job, mark_processing, mark_done, mark_error, fail_stuck_jobs
from app.ai.pose import detect_torso_anchor_mediapipe
from app.ai.image_utils import garment_cutout_auto_bgra, overlay_bgra_on_bgr


def _read_bgr(path: str):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Failed to read image: {path}")
    return img


def process_one(job_id: str) -> bool:
    db = SessionLocal()
    try:
        job = get_job(db, UUID(job_id))
        if not job:
            return False

        if job.status not in ("queued", "processing"):
            return False

        try:
            mark_processing(db, job)
            job_log(job_id, "processing started")

            person_bgr = _read_bgr(job.person_image_path)
            garment_bgr = _read_bgr(job.garment_image_path)

            anchor = detect_torso_anchor_mediapipe(person_bgr)
            if anchor is None:
                raise ValueError("POSE_NOT_FOUND")

            garment_bgra = garment_cutout_auto_bgra(garment_bgr)

            garment_resized = cv2.resize(
                garment_bgra, (anchor.w, anchor.h), interpolation=cv2.INTER_AREA
            )

            out_bgr = overlay_bgra_on_bgr(person_bgr, garment_resized, anchor.x, anchor.y)

            out_path = RESULTS_DIR / f"{job.id}.png"
            ok = cv2.imwrite(str(out_path), out_bgr)
            if not ok:
                raise RuntimeError("WRITE_FAILED")

            mark_done(db, job, str(out_path))
            job_log(job_id, f"done -> {out_path.name}")
            return True

        except Exception as e:
            msg = str(e)
            if msg == "POSE_NOT_FOUND":
                code = "POSE_NOT_FOUND"
                human = "Não foi possível detectar ombros/torso. Use foto frontal com corpo visível."
            elif msg == "WRITE_FAILED":
                code = "WRITE_FAILED"
                human = "Falha ao salvar imagem resultado."
            else:
                code = "WORKER_ERROR"
                human = f"{type(e).__name__}: {e}"

            mark_error(db, job, code, human)
            job_log(job_id, f"ERROR {code}: {human}")
            job_log(job_id, traceback.format_exc())
            return False

    finally:
        db.close()


def loop():
    print("Worker iniciado. Aguardando jobs queued... (CTRL+C para sair)")
    while True:
        db = SessionLocal()
        try:
            fail_stuck_jobs(db, timeout_seconds=240)

            stmt = select(TryOnJob).where(TryOnJob.status == "queued").order_by(TryOnJob.created_at.asc()).limit(1)
            job = db.execute(stmt).scalar_one_or_none()

            if not job:
                time.sleep(1.0)
                continue

            process_one(str(job.id))

        finally:
            db.close()


if __name__ == "__main__":
    loop()

from app.workers.worker import loop

if __name__ == "__main__":
    loop()
