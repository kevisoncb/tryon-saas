from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from uuid import UUID, uuid4

import redis
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from rq import Queue
from sqlalchemy.orm import Session

from auth import require_api_key
from crud import create_tryon_job, get_tryon_job
from database import get_db
from schemas import TryOnCreateResponse, TryOnStatusResponse
from tasks import process_tryon_job

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RESULTS_DIR = STORAGE_DIR / "results"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()

app = FastAPI(title="TryOn SaaS API", version="1.1.0")
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")


def _save_upload(file: UploadFile, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = file.file.read()
    with out_path.open("wb") as f:
        f.write(content)


def _result_url_for_job(job_id: UUID) -> str:
    return f"{API_BASE_URL}/tryon/{job_id}/result"


def _get_queue() -> Queue:
    r = redis.from_url(REDIS_URL)
    return Queue("tryon", connection=r)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/tryon", response_model=TryOnCreateResponse)
def create_tryon(
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    db: Session = Depends(get_db),
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

    # Enfileira o job (RQ)
    q = _get_queue()
    q.enqueue(process_tryon_job, str(job.id), job_timeout=600)

    return TryOnCreateResponse(job_id=job.id, status=job.status)


@app.get("/tryon/{job_id}", response_model=TryOnStatusResponse)
def get_tryon(job_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_api_key)):
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


@app.get("/tryon/{job_id}/result")
def get_tryon_result(job_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_api_key)):
    job = get_tryon_job(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("queued", "processing"):
        raise HTTPException(status_code=409, detail=f"Job not ready (status={job.status})")
    if job.status == "error":
        raise HTTPException(status_code=409, detail=f"Job errored: {job.error_message}")

    if not job.result_image_path:
        raise HTTPException(status_code=500, detail="Job done but no result_image_path")

    p = Path(job.result_image_path)
    if not p.exists():
        raise HTTPException(status_code=500, detail="Result file missing on disk")

    media_type = mimetypes.guess_type(str(p))[0] or "image/png"
    return FileResponse(
        path=str(p),
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )
