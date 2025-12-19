# backend/alembic/env.py
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------
# Garante que "backend/" esteja no sys.path (para importar app/ e setting.py)
# ---------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[1]  # .../backend
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from setting import DATABASE_URL  # noqa: E402
from app.infra.db.database import Base  # noqa: E402
import app.infra.db.models  # noqa: E402  # registra tabelas no Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return DATABASE_URL


def run_migrations_offline() -> None:
    url = get_url()
    is_sqlite = url.startswith("sqlite")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Em SQLite, comparar tipo gera falso positivo (UUID vira NUMERIC)
        compare_type=not is_sqlite,
        compare_server_default=True,
        # Batch mode é recomendado em SQLite
        render_as_batch=is_sqlite,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        dialect_name = connection.dialect.name
        is_sqlite = dialect_name == "sqlite"

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Em SQLite, comparar tipo gera falso positivo (UUID vira NUMERIC)
            compare_type=not is_sqlite,
            compare_server_default=True,
            # Batch mode para alterações que SQLite suporta via “recreate table”
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
