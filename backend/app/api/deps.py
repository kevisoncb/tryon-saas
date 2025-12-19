from __future__ import annotations

from fastapi import Depends

from app.security.auth import require_api_key
from app.infra.db.database import get_db

# Centraliza dependencies
db_dep = Depends(get_db)
api_key_dep = Depends(require_api_key)
