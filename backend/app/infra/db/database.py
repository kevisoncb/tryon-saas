# backend/app/infra/db/database.py
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from settings import DATABASE_URL

# Engine
_engine_kwargs = {
    "pool_pre_ping": True,
    "future": True,
}

# SQLite precisa de connect_args específicos
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

# Base (models herdam daqui)
Base = declarative_base()


def init_db() -> None:
    """
    Cria tabelas (MVP). Em produção, prefira Alembic (migrações).
    """
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator:
    """
    Dependency do FastAPI.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
