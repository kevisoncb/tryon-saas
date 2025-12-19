# backend/app/infra/db/crud.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.infra.db.models import ApiKey, TryOnJob


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -----------------------------
# API KEYS
# -----------------------------
def get_api_key(db: Session, key: str) -> Optional[ApiKey]:
    stmt = select(ApiKey).where(ApiKey.key == key, ApiKey.is_active.is_(True))
    return db.execute(stmt).scalar_one_or_none()


# -----------------------------
# JOBS
# -----------------------------
def create_job(db: Session, person_path: str, garment_path: str) -> TryOnJob:
    job = TryOnJob(
        person_image_path=person_path,
        garment_image_path=garment_path,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: UUID) -> Optional[TryOnJob]:
    stmt = select(TryOnJob).where(TryOnJob.id == job_id)
    return db.execute(stmt).scalar_one_or_none()


def list_jobs(db: Session, status: Optional[str], limit: int = 50) -> List[TryOnJob]:
    stmt = select(TryOnJob).order_by(TryOnJob.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(TryOnJob.status == status)
    return list(db.execute(stmt).scalars().all())


def mark_processing(db: Session, job: TryOnJob) -> None:
    job.status = "processing"
    job.processing_started_at = utcnow()
    job.error_code = None
    job.error_message = None
    job.attempts = int(job.attempts or 0) + 1
    db.commit()


def mark_done(db: Session, job: TryOnJob, result_path: str) -> None:
    job.status = "done"
    job.result_image_path = result_path
    job.completed_at = utcnow()
    job.error_code = None
    job.error_message = None
    db.commit()


def mark_error(db: Session, job: TryOnJob, error_code: str, error_message: str) -> None:
    job.status = "error"
    job.error_code = error_code
    job.error_message = (error_message or "")[:2000]
    job.completed_at = utcnow()
    db.commit()


def fail_stuck_jobs(db: Session, timeout_seconds: int = 240) -> int:
    """
    Jobs travados em processing por muito tempo viram error.
    Baseado no seu fluxo atual (processing_started_at). :contentReference[oaicite:2]{index=2}
    """
    now = utcnow()
    cutoff = now - timedelta(seconds=timeout_seconds)

    stmt = select(TryOnJob).where(
        TryOnJob.status == "processing",
        TryOnJob.processing_started_at.is_not(None),
        TryOnJob.processing_started_at < cutoff,
    )
    jobs = list(db.execute(stmt).scalars().all())

    for j in jobs:
        j.status = "error"
        j.error_code = "WORKER_TIMEOUT"
        j.error_message = "Job ficou travado em processing e foi finalizado por timeout."
        j.completed_at = now

    if jobs:
        db.commit()

    return len(jobs)


def claim_next_job(db: Session) -> Optional[TryOnJob]:
    """
    Tenta fazer claim atômico do próximo job queued.
    Ideal para múltiplos workers: evita pegar o mesmo job duas vezes.

    - Postgres/MySQL: tenta usar SELECT ... FOR UPDATE SKIP LOCKED
    - SQLite: fallback (não suporta SKIP LOCKED de forma equivalente)
    """
    try:
        # Preferência: lock pessimista com skip_locked
        stmt = (
            select(TryOnJob)
            .where(TryOnJob.status == "queued")
            .order_by(TryOnJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = db.execute(stmt).scalar_one_or_none()
        if not job:
            db.rollback()
            return None

        # Claim efetivo
        job.status = "processing"
        job.processing_started_at = utcnow()
        job.error_code = None
        job.error_message = None
        job.attempts = int(job.attempts or 0) + 1
        db.commit()
        db.refresh(job)
        return job

    except (OperationalError, TypeError):
        # Fallback quando o backend/driver não suporta FOR UPDATE SKIP LOCKED
        db.rollback()
        stmt = (
            select(TryOnJob)
            .where(TryOnJob.status == "queued")
            .order_by(TryOnJob.created_at.asc())
            .limit(1)
        )
        job = db.execute(stmt).scalar_one_or_none()
        if not job:
            return None

        # Best effort: marcar processing rapidamente
        job.status = "processing"
        job.processing_started_at = utcnow()
        job.error_code = None
        job.error_message = None
        job.attempts = int(job.attempts or 0) + 1
        db.commit()
        db.refresh(job)
        return job
