from __future__ import annotations

from typing import Optional
from uuid import UUID
from datetime import timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text

from models import TryOnJob


def create_job(db: Session, person_path: str, garment_path: str) -> TryOnJob:
    job = TryOnJob(
        status="queued",
        person_image_path=person_path,
        garment_image_path=garment_path,
        result_image_path=None,
        error_message=None,
        last_error=None,
        attempts=0,
        processing_started_at=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: UUID) -> Optional[TryOnJob]:
    return db.query(TryOnJob).filter(TryOnJob.id == job_id).first()


def set_done(db: Session, job: TryOnJob, result_path: str) -> TryOnJob:
    job.status = "done"
    job.result_image_path = result_path
    job.error_message = None
    job.last_error = None
    job.processing_started_at = None
    db.commit()
    db.refresh(job)
    return job


def set_error(db: Session, job: TryOnJob, message: str) -> TryOnJob:
    job.status = "error"
    job.error_message = message
    job.last_error = message
    job.processing_started_at = None
    db.commit()
    db.refresh(job)
    return job


def claim_next_job_atomic(db: Session, max_attempts: int = 3) -> Optional[TryOnJob]:
    """
    Claim atômico com FOR UPDATE SKIP LOCKED.
    - evita duplicidade entre workers
    - incrementa attempts
    - seta processing_started_at
    """
    row = db.execute(
        text(
            """
            WITH next_job AS (
              SELECT id
              FROM tryon_jobs
              WHERE status = 'queued'
                AND attempts < :max_attempts
              ORDER BY created_at ASC
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE tryon_jobs j
            SET status = 'processing',
                processing_started_at = now(),
                attempts = j.attempts + 1,
                last_error = NULL,
                error_message = NULL,
                updated_at = now()
            FROM next_job
            WHERE j.id = next_job.id
            RETURNING j.id;
            """
        ),
        {"max_attempts": max_attempts},
    ).fetchone()

    if not row:
        db.commit()
        return None

    db.commit()
    return db.query(TryOnJob).filter(TryOnJob.id == row[0]).first()


def requeue_stuck_jobs(
    db: Session,
    timeout_minutes: int = 5,
    max_attempts: int = 3,
) -> int:
    """
    Watchdog:
    - jobs em processing há mais de timeout -> volta para queued (se ainda tem tentativas)
    - se estourou tentativas -> vira error
    Retorna quantos jobs foram afetados.
    """
    # 1) volta para queued se ainda pode tentar
    requeued = db.execute(
        text(
            """
            UPDATE tryon_jobs
            SET status = 'queued',
                last_error = COALESCE(last_error, '') || CASE WHEN last_error IS NULL OR last_error = '' THEN '' ELSE E'\n' END
                             || 'Watchdog: job preso em processing, requeue.',
                processing_started_at = NULL,
                updated_at = now()
            WHERE status = 'processing'
              AND processing_started_at IS NOT NULL
              AND processing_started_at < now() - (:timeout || ' minutes')::interval
              AND attempts < :max_attempts
            """
        ),
        {"timeout": timeout_minutes, "max_attempts": max_attempts},
    ).rowcount

    # 2) marca erro se já estourou tentativas
    errored = db.execute(
        text(
            """
            UPDATE tryon_jobs
            SET status = 'error',
                error_message = 'Job travado e excedeu tentativas máximas.',
                last_error = COALESCE(last_error, '') || CASE WHEN last_error IS NULL OR last_error = '' THEN '' ELSE E'\n' END
                             || 'Watchdog: job preso em processing e excedeu tentativas.',
                processing_started_at = NULL,
                updated_at = now()
            WHERE status = 'processing'
              AND processing_started_at IS NOT NULL
              AND processing_started_at < now() - (:timeout || ' minutes')::interval
              AND attempts >= :max_attempts
            """
        ),
        {"timeout": timeout_minutes, "max_attempts": max_attempts},
    ).rowcount

    db.commit()
    return int((requeued or 0) + (errored or 0))
