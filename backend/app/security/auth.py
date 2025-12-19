from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.infra.db.database import get_db
from app.infra.db.crud import get_api_key


def require_api_key(
    x_api_key: str = Header(default="", alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> str:
    if not x_api_key:
        raise HTTPException(status_code=401, detail={"error_code": "NO_API_KEY", "message": "Missing X-API-Key"})
    row = get_api_key(db, x_api_key)
    if not row:
        raise HTTPException(status_code=401, detail={"error_code": "INVALID_API_KEY", "message": "Invalid API key"})
    return x_api_key
