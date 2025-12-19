# backend/scripts/init_db.py
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # .../backend
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.infra.db.database import SessionLocal  # noqa: E402
from app.infra.db.crud import ensure_default_plans  # noqa: E402


def main() -> None:
    """
    Inicialização pós-migração.
    Rode antes: alembic upgrade head
    """
    db = SessionLocal()
    try:
        ensure_default_plans(db)
        print("Planos default garantidos (free/pro).")
    finally:
        db.close()

    print("Init pós-migração finalizado.")


if __name__ == "__main__":
    main()
