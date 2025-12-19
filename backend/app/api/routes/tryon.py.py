from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from settings import UPLOADS_DIR
from app.api.deps import rate_limit
from app.infra.db.database import get_db
from app.infra.db.crud import create_job, get_job


router = APIRouter(prefix="/tryon", tags=["tryon"])


@router.post("")
def create_tryon(
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    _api_key: str = Depends(rate_limit),
    db: Session = Depends(get_db),
):
    if not (person_image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail={"error_code": "INVALID_PERSON_FILE", "message": "person_image must be an image"})
    if not (garment_image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail={"error_code": "INVALID_GARMENT_FILE", "message": "garment_image must be an image"})

    temp_id = UUID(bytes=os.urandom(16), version=4)
    person_path = UPLOADS_DIR / f"{temp_id}_person.jpg"
    garment_path = UPLOADS_DIR / f"{temp_id}_garment.jpg"

    person_path.write_bytes(person_image.file.read())
    garment_path.write_bytes(garment_image.file.read())

    job = create_job(db, str(person_path), str(garment_path))
    return {"job_id": str(job.id), "status": job.status}


@router.get("/{job_id}")
def get_tryon_status(
    job_id: str,
    _api_key: str = Depends(rate_limit),
    db: Session = Depends(get_db),
):
    job = get_job(db, UUID(job_id))
    if not job:
        raise HTTPException(status_code=404, detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"})

    return {
        "job_id": str(job.id),
        "status": job.status,
        "person_image_path": job.person_image_path,
        "garment_image_path": job.garment_image_path,
        "result_image_path": job.result_image_path,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


@router.get("/{job_id}/result")
def get_tryon_result(
    job_id: str,
    _api_key: str = Depends(rate_limit),
    db: Session = Depends(get_db),
):
    job = get_job(db, UUID(job_id))
    if not job:
        raise HTTPException(status_code=404, detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"})

    if job.status in ("queued", "processing"):
        raise HTTPException(status_code=409, detail={"error_code": "JOB_NOT_READY", "message": f"Job not ready: {job.status}"})

    if job.status == "error":
        raise HTTPException(status_code=409, detail={
            "error_code": "JOB_ERROR",
            "message": f"Job errored: {job.error_code}",
            "details": {"error_message": job.error_message},
        })

    if not job.result_image_path or not Path(job.result_image_path).exists():
        raise HTTPException(status_code=404, detail={"error_code": "RESULT_NOT_FOUND", "message": "Result file not found"})

    return FileResponse(job.result_image_path, media_type="image/png")
