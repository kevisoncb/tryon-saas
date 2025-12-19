from __future__ import annotations

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.infra.db.database import SessionLocal
from app.infra.db.models import ApiKey


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    db: Session = SessionLocal()
    try:
        key = db.query(ApiKey).filter(ApiKey.key == x_api_key, ApiKey.is_active == True).first()  # noqa: E712
        if not key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return x_api_key
    finally:
        db.close()
