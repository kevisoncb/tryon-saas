from fastapi import Depends
from sqlalchemy.orm import Session

from app.infra.db.database import get_db
from app.infra.db.crud import get_api_key
from app.security.auth import require_api_key
from app.security.rate_limiter import SimpleRateLimiter

limiter = SimpleRateLimiter()


def rate_limit(
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> str:
    row = get_api_key(db, api_key)
    if row:
        limiter.check(api_key, int(row.rpm_limit or 60))
    return api_key
