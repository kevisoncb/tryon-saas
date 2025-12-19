from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.paths import STORAGE_DIR
from app.api.routes.tryon import router as tryon_router
from app.api.routes.garment import router as garment_router

app = FastAPI(title="TryOn SaaS API", version="2.1.0")

app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

app.include_router(tryon_router)
app.include_router(garment_router)


@app.get("/health")
def health():
    return {"ok": True}
