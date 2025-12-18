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
