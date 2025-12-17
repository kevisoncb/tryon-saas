from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
from PIL import Image
import uuid

from database import SessionLocal
from models import TryOnJob

app = FastAPI(title="TryOn SaaS")

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "storage" / "uploads"
RESULTS_DIR = BASE_DIR / "storage" / "results"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------
# DEPENDÊNCIA DO BANCO
# -------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------------------------------
# HEALTH
# -------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

# -------------------------------------------------
# CRIAR TRY-ON
# -------------------------------------------------
@app.post("/tryon")
async def create_tryon(
    person: UploadFile = File(...),
    garment: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not (person.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Arquivo 'person' deve ser imagem.")

    if not (garment.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Arquivo 'garment' deve ser imagem.")

    job_id = uuid.uuid4()

    person_path = UPLOADS_DIR / f"{job_id}_person.jpg"
    garment_path = UPLOADS_DIR / f"{job_id}_garment.jpg"
    result_path = RESULTS_DIR / f"{job_id}.png"

    person_path.write_bytes(await person.read())
    garment_path.write_bytes(await garment.read())

    _make_mock_result(person_path, garment_path, result_path)

    job = TryOnJob(
        id=job_id,
        status="done",
        person_image_path=str(person_path),
        garment_image_path=str(garment_path),
        result_image_path=str(result_path),
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return {
        "job_id": job.id,   # UUID puro (FastAPI serializa)
        "status": job.status
    }

# -------------------------------------------------
# CONSULTAR STATUS
# -------------------------------------------------
@app.get("/tryon/{job_id}")
def get_tryon(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.query(TryOnJob).filter(TryOnJob.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    return {
        "job_id": job.id,
        "status": job.status
    }

# -------------------------------------------------
# BAIXAR RESULTADO
# -------------------------------------------------
@app.get("/tryon/{job_id}/result")
def get_result(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.query(TryOnJob).filter(TryOnJob.id == job_id).first()

    if not job or not job.result_image_path:
        raise HTTPException(status_code=404, detail="Resultado não encontrado.")

    return FileResponse(job.result_image_path)

# -------------------------------------------------
# MOCK DO TRY-ON (TEMPORÁRIO)
# -------------------------------------------------
def _make_mock_result(person_path: Path, garment_path: Path, out_path: Path):
    person = Image.open(person_path).convert("RGBA")
    garment = Image.open(garment_path).convert("RGBA")

    target_w = int(person.width * 0.45)
    scale = target_w / garment.width
    target_h = int(garment.height * scale)

    garment = garment.resize((target_w, target_h))

    x = int((person.width - target_w) / 2)
    y = int(person.height * 0.25)

    person.alpha_composite(garment, (x, y))
    person.save(out_path)
