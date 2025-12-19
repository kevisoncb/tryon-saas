# backend/app/security/auth.py
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.infra.db.crud import get_api_key
from app.infra.db.database import get_db
from app.infra.db.models import ApiKey


def require_api_key(
    x_api_key: str = Header(default="", alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> ApiKey:
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "NO_API_KEY", "message": "Missing X-API-Key"},
        )

    row = get_api_key(db, x_api_key)
    if not row:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "INVALID_API_KEY", "message": "Invalid API key"},
        )

    return row
