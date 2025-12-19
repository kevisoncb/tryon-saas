from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.paths import STORAGE_DIR
from app.api.routes.tryon import router as tryon_router

app = FastAPI(title="TryOn SaaS API", version="2.0.0")

# Servir storage
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

# Rotas
app.include_router(tryon_router)


@app.get("/health")
def health():
    return {"ok": True}
