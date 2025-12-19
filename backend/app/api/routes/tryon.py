# backend/app/api/routes/tryon.py
from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import rate_limit
from app.infra.db.crud import create_job, get_job
from app.infra.db.database import get_db
from app.infra.db.models import ApiKey
from settings import UPLOADS_DIR


router = APIRouter(prefix="/tryon", tags=["tryon"])

# Hardening básico para uploads no MVP
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_upload_or_413(upload: UploadFile, max_bytes: int) -> bytes:
    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "error_code": "FILE_TOO_LARGE",
                "message": f"File exceeds max size of {max_bytes} bytes",
            },
        )
    if not data:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "EMPTY_FILE", "message": "Uploaded file is empty"},
        )
    return data


def _as_storage_url(path_str: str | None) -> str | None:
    if not path_str:
        return None
    name = Path(path_str).name
    return f"/storage/{name}"


@router.post("")
def create_tryon(
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    api_key: ApiKey = Depends(rate_limit),
    db: Session = Depends(get_db),
):
    if not (person_image.content_type or "").startswith("image/"):
        raise HTTPException(
            status_code=415,
            detail={
                "error_code": "INVALID_PERSON_FILE",
                "message": "person_image must be an image",
            },
        )

    if not (garment_image.content_type or "").startswith("image/"):
        raise HTTPException(
            status_code=415,
            detail={
                "error_code": "INVALID_GARMENT_FILE",
                "message": "garment_image must be an image",
            },
        )

    _ensure_dir(UPLOADS_DIR)

    temp_id = uuid4()

    person_path = UPLOADS_DIR / f"{temp_id}_person.jpg"
    garment_path = UPLOADS_DIR / f"{temp_id}_garment.jpg"

    person_bytes = _read_upload_or_413(person_image, MAX_UPLOAD_BYTES)
    garment_bytes = _read_upload_or_413(garment_image, MAX_UPLOAD_BYTES)

    person_path.write_bytes(person_bytes)
    garment_path.write_bytes(garment_bytes)

    job = create_job(db, str(person_path), str(garment_path))

    return {
        "job_id": str(job.id),
        "status": job.status,
        "person_url": _as_storage_url(job.person_image_path),
        "garment_url": _as_storage_url(job.garment_image_path),
    }


@router.get("/{job_id}")
def get_tryon_status(
    job_id: str,
    api_key: ApiKey = Depends(rate_limit),
    db: Session = Depends(get_db),
):
    job = get_job(db, UUID(job_id))
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"},
        )

    return {
        "job_id": str(job.id),
        "status": job.status,
        "result_url": _as_storage_url(job.result_image_path),
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


@router.get("/{job_id}/result")
def get_tryon_result(
    job_id: str,
    api_key: ApiKey = Depends(rate_limit),
    db: Session = Depends(get_db),
):
    job = get_job(db, UUID(job_id))
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"},
        )

    if job.status in ("queued", "processing"):
        raise HTTPException(
            status_code=409,
            detail={"error_code": "JOB_NOT_READY", "message": f"Job not ready: {job.status}"},
        )

    if job.status == "error":
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "JOB_ERROR",
                "message": f"Job errored: {job.error_code}",
                "details": {"error_message": job.error_message},
            },
        )

    if not job.result_image_path or not Path(job.result_image_path).exists():
        raise HTTPException(
            status_code=404,
            detail={"error_code": "RESULT_NOT_FOUND", "message": "Result file not found"},
        )

    # Se seu pipeline escreve PNG, mantenha image/png (se escreve JPG, ajuste aqui)
    return FileResponse(job.result_image_path, media_type="image/png")
