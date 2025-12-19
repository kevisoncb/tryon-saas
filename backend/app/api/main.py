from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from settings import API_TITLE, API_VERSION, STORAGE_DIR
from app.api.routes.tryon import router as tryon_router
from app.api.routes.garment import router as garment_router
from app.api.routes.admin import router as admin_router


def create_app() -> FastAPI:
    app = FastAPI(title=API_TITLE, version=API_VERSION)

    app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

    @app.get("/health")
    def health():
        return {"ok": True}

    app.include_router(garment_router)
    app.include_router(tryon_router)
    app.include_router(admin_router)

    return app


app = create_app()
