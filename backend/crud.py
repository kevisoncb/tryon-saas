from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from models import TryOnJob


def create_job(db: Session, person_path: str, garment_path: str) -> TryOnJob:
    job = TryOnJob(
        status="queued",
        person_image_path=person_path,
        garment_image_path=garment_path,
        result_image_path=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: UUID) -> Optional[TryOnJob]:
    return db.query(TryOnJob).filter(TryOnJob.id == job_id).first()


def update_job_paths(db: Session, job: TryOnJob, person_path: str, garment_path: str) -> TryOnJob:
    job.person_image_path = person_path
    job.garment_image_path = garment_path
    db.commit()
    db.refresh(job)
    return job


def update_job_status(db: Session, job: TryOnJob, status: str, result_path: Optional[str] = None) -> TryOnJob:
    job.status = status
    if result_path is not None:
        job.result_image_path = result_path
    db.commit()
    db.refresh(job)
    return job

from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select

from models import TryOnJob


def create_job(db: Session, person_path: str, garment_path: str) -> TryOnJob:
    job = TryOnJob(
        status="queued",
        person_image_path=person_path,
        garment_image_path=garment_path,
        result_image_path=None,
        error_message=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: UUID) -> Optional[TryOnJob]:
    return db.query(TryOnJob).filter(TryOnJob.id == job_id).first()


def set_processing(db: Session, job: TryOnJob) -> TryOnJob:
    job.status = "processing"
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job


def set_done(db: Session, job: TryOnJob, result_path: str) -> TryOnJob:
    job.status = "done"
    job.result_image_path = result_path
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job


def set_error(db: Session, job: TryOnJob, message: str) -> TryOnJob:
    job.status = "error"
    job.error_message = message
    db.commit()
    db.refresh(job)
    return job


def claim_next_job(db: Session) -> Optional[TryOnJob]:
    """
    Pega 1 job queued mais antigo e "trava" ele para processamento.
    Implementação simples (boa para dev local).
    """
    job = (
        db.query(TryOnJob)
        .filter(TryOnJob.status == "queued")
        .order_by(TryOnJob.created_at.asc())
        .first()
    )
    if not job:
        return None

    job.status = "processing"
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job
