import os
import shutil
from uuid import UUID
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import SessionLocal
from schemas import TryOnCreateResponse, TryOnStatusResponse
from crud import create_job, get_job
from auth import require_api_key

app = FastAPI(title="TryOn SaaS API", version="0.4.0")

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RESULTS_DIR = STORAGE_DIR / "results"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {"ok": True}


def _safe_suffix(filename: str, default: str) -> str:
    suf = Path(filename).suffix.lower().strip()
    if suf in (".png", ".jpg", ".jpeg", ".webp"):
        return suf
    return default


@app.post("/tryon", response_model=TryOnCreateResponse)
def create_tryon(
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    db: Session = Depends(get_db),
    api_key=Depends(require_api_key),
):
    # salvar temporários
    tmp_person = UPLOADS_DIR / f"tmp_person_{os.urandom(8).hex()}_{person_image.filename}"
    tmp_garment = UPLOADS_DIR / f"tmp_garment_{os.urandom(8).hex()}_{garment_image.filename}"

    with tmp_person.open("wb") as f:
        shutil.copyfileobj(person_image.file, f)
    with tmp_garment.open("wb") as f:
        shutil.copyfileobj(garment_image.file, f)

    # criar job no DB com paths temporários
    job = create_job(db, str(tmp_person), str(tmp_garment))

    # renomear arquivos para incluir job_id
    person_ext = _safe_suffix(person_image.filename, ".jpg")
    garment_ext = _safe_suffix(garment_image.filename, ".png")

    final_person = UPLOADS_DIR / f"{job.id}_person{person_ext}"
    final_garment = UPLOADS_DIR / f"{job.id}_garment{garment_ext}"

    tmp_person.replace(final_person)
    tmp_garment.replace(final_garment)

    # atualizar paths finais no DB
    job.person_image_path = str(final_person)
    job.garment_image_path = str(final_garment)
    job.api_key_id = api_key.id
    db.commit()
    db.refresh(job)

    return TryOnCreateResponse(job_id=job.id, status=job.status)


@app.get("/tryon/{job_id}", response_model=TryOnStatusResponse)
def tryon_status(
    job_id: UUID,
    db: Session = Depends(get_db),
    api_key=Depends(require_api_key),
):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # proteção: só o dono vê
    if job.api_key_id and job.api_key_id != api_key.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return TryOnStatusResponse(
        job_id=job.id,
        status=job.status,
        person_image_path=job.person_image_path,
        garment_image_path=job.garment_image_path,
        result_image_path=job.result_image_path,
        error_message=getattr(job, "error_message", None),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@app.get("/tryon/{job_id}/result")
def tryon_result(
    job_id: UUID,
    db: Session = Depends(get_db),
    api_key=Depends(require_api_key),
):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.api_key_id and job.api_key_id != api_key.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if job.status == "error":
        raise HTTPException(status_code=409, detail=f"Job errored: {job.error_message}")

    if job.status != "done" or not job.result_image_path:
        raise HTTPException(status_code=409, detail=f"Job not ready (status={job.status})")

    path = Path(job.result_image_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file not found on disk")

    return FileResponse(path)
