from __future__ import annotations

from app.infra.db.database import engine
from app.infra.db.models import Base

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Banco inicializado com sucesso.")
