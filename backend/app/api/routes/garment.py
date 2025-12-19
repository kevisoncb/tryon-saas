from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import rate_limit
from app.infra.db.database import get_db
from app.ai.image_utils import decode_upload_to_bgr, validate_garment_photo, garment_cutout_auto_bgra, encode_png_rgba

router = APIRouter(prefix="/garment", tags=["garment"])


@router.post("/validate")
def garment_validate(
    garment_image: UploadFile = File(...),
    _api_key: str = Depends(rate_limit),
):
    bgr = decode_upload_to_bgr(garment_image)
    return validate_garment_photo(bgr)


@router.post("/cutout")
def garment_cutout(
    garment_image: UploadFile = File(...),
    _api_key: str = Depends(rate_limit),
):
    bgr = decode_upload_to_bgr(garment_image)
    report = validate_garment_photo(bgr)
    if (not report["ok"]) and report["score"] < 0.35:
        raise HTTPException(status_code=422, detail={
            "error_code": "GARMENT_IMAGE_LOW_QUALITY",
            "message": "Imagem da roupa com qualidade insuficiente para recorte confiável.",
            "details": report,
        })

    bgra = garment_cutout_auto_bgra(bgr)
    png_bytes = encode_png_rgba(bgra)
    return Response(content=png_bytes, media_type="image/png")
