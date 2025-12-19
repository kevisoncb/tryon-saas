from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from database import SessionLocal
from rate_limiter import InMemoryRateLimiter
from models import ApiKey

limiter = InMemoryRateLimiter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_api_key(
    x_api_key: str = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")

    api_key = db.query(ApiKey).filter(ApiKey.key == x_api_key).first()
    if not api_key or not api_key.is_active:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Rate limit por chave
    limit = api_key.rpm_limit or 60
    ok = limiter.allow(key=x_api_key, limit=limit, window_seconds=60)
    if not ok:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded ({limit}/min)")

    return api_key
