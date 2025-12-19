from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.infra.db.models import TryOnJob


def create_tryon_job(db: Session, job_id: UUID, person_image_path: str, garment_image_path: str) -> TryOnJob:
    job = TryOnJob(
        id=job_id,
        status="queued",
        person_image_path=person_image_path,
        garment_image_path=garment_image_path,
        result_image_path=None,
        error_message=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_tryon_job(db: Session, job_id: UUID) -> TryOnJob | None:
    return db.query(TryOnJob).filter(TryOnJob.id == job_id).first()
