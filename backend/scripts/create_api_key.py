from __future__ import annotations

import secrets

from app.infra.db.database import SessionLocal
from app.infra.db.models import ApiKey

if __name__ == "__main__":
    name = "local-dev"
    key = secrets.token_urlsafe(32)

    db = SessionLocal()
    try:
        obj = ApiKey(name=name, key=key, is_active=True, rpm_limit=60)
        db.add(obj)
        db.commit()
        print("API KEY criada:")
        print(key)
    finally:
        db.close()
