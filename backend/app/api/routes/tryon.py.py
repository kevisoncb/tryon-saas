from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from rq import Queue
from sqlalchemy.orm import Session

from app.api.schemas.tryon import TryOnCreateResponse, TryOnStatusResponse
from app.core.config import API_BASE_URL
from app.core.paths import STORAGE_DIR, UPLOADS_DIR
from app.infra.db.crud import create_tryon_job, get_tryon_job
from app.infra.queue.rq import get_queue
from app.security.auth import require_api_key
from app.workers.tasks import process_tryon_job

router = APIRouter(tags=["tryon"])


def _save_upload(file: UploadFile, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(file.file.read())


def _result_url_for_job(job_id: UUID) -> str:
    return f"{API_BASE_URL}/tryon/{job_id}/result"


@router.post("/tryon", response_model=TryOnCreateResponse)
def create_tryon(
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    db: Session = Depends(lambda: next(__import__("app.infra.db.database").infra.db.database.get_db())),
    _: str = Depends(require_api_key),
):
    job_id = uuid4()

    person_path = UPLOADS_DIR / f"{job_id}_person.jpg"
    garment_path = UPLOADS_DIR / f"{job_id}_garment.jpg"
    _save_upload(person_image, person_path)
    _save_upload(garment_image, garment_path)

    job = create_tryon_job(
        db=db,
        job_id=job_id,
        person_image_path=str(person_path),
        garment_image_path=str(garment_path),
    )

    q: Queue = get_queue()
    q.enqueue(process_tryon_job, str(job.id), job_timeout=600)

    return TryOnCreateResponse(job_id=job.id, status=job.status)


@router.get("/tryon/{job_id}", response_model=TryOnStatusResponse)
def get_tryon_status(
    job_id: UUID,
    db: Session = Depends(lambda: next(__import__("app.infra.db.database").infra.db.database.get_db())),
    _: str = Depends(require_api_key),
):
    job = get_tryon_job(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result_url = None
    if job.status == "done":
        result_url = _result_url_for_job(job.id)

    return TryOnStatusResponse(
        job_id=job.id,
        status=job.status,
        person_image_path=job.person_image_path,
        garment_image_path=job.garment_image_path,
        result_image_path=job.result_image_path,
        result_url=result_url,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/tryon/{job_id}/result")
def get_tryon_result(
    job_id: UUID,
    db: Session = Depends(lambda: next(__import__("app.infra.db.database").infra.db.database.get_db())),
    _: str = Depends(require_api_key),
):
    job = get_tryon_job(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("queued", "processing"):
        raise HTTPException(status_code=409, detail=f"Job not ready (status={job.status})")
    if job.status == "error":
        raise HTTPException(status_code=409, detail=f"Job errored: {job.error_message}")

    if not job.result_image_path:
        raise HTTPException(status_code=500, detail="Job done but no result_image_path stored")

    p = Path(job.result_image_path)
    if not p.exists():
        raise HTTPException(status_code=500, detail="Result file missing on disk")

    media_type = mimetypes.guess_type(str(p))[0] or "image/png"
    return FileResponse(str(p), media_type=media_type, headers={"Cache-Control": "no-store"})
