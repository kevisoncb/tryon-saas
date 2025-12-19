"""baseline schema

Revision ID: 0001_baseline
Revises: 
Create Date: 2025-12-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline: criar todas as tabelas do metadata atual.
    # Isso evita autogenerate tentar ALTER COLUMN no SQLite.
    bind = op.get_bind()
    meta = sa.MetaData()
    meta.reflect(bind=bind)  # no-op em DB vazio
    # O create_all abaixo NÃO cria a partir do meta refletido, então fazemos via import do Base:
    from app.infra.db.database import Base  # import local para evitar problemas de import no topo

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    from app.infra.db.database import Base

    Base.metadata.drop_all(bind=bind)
