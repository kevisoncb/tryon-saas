from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.infra.db.models import TryOnJob, ApiKey


def get_api_key(db: Session, key: str) -> Optional[ApiKey]:
    stmt = select(ApiKey).where(ApiKey.key == key, ApiKey.is_active.is_(True))
    return db.execute(stmt).scalar_one_or_none()


def create_job(db: Session, person_path: str, garment_path: str) -> TryOnJob:
    job = TryOnJob(person_image_path=person_path, garment_image_path=garment_path, status="queued")
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
    job.processing_started_at = datetime.now(timezone.utc)
    job.error_code = None
    job.error_message = None
    job.attempts = int(job.attempts or 0) + 1
    db.commit()


def mark_done(db: Session, job: TryOnJob, result_path: str) -> None:
    job.status = "done"
    job.result_image_path = result_path
    job.completed_at = datetime.now(timezone.utc)
    job.error_code = None
    job.error_message = None
    db.commit()


def mark_error(db: Session, job: TryOnJob, error_code: str, error_message: str) -> None:
    job.status = "error"
    job.error_code = error_code
    job.error_message = (error_message or "")[:2000]
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


def fail_stuck_jobs(db: Session, timeout_seconds: int = 240) -> int:
    now = datetime.now(timezone.utc)
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
