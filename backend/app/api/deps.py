# backend/app/api/deps.py
from __future__ import annotations

from fastapi import Depends

from app.infra.db.models import ApiKey
from app.security.auth import require_api_key
from app.security.rate_limiter import SimpleRateLimiter

limiter = SimpleRateLimiter()


def rate_limit(api_key: ApiKey = Depends(require_api_key)) -> ApiKey:
    rpm = int(api_key.rpm_limit or 60)
    limiter.check(api_key.key, rpm)
    return api_key
