"""Adiciona controle de tentativas e atualizado_em em postagens para Worker resiliente.

Revision ID: 0003_postagem_resiliencia_worker
Revises: 0002_rag_hibrido_brand_bible
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_postagem_resiliencia_worker"
down_revision: str | Sequence[str] | None = "0002_rag_hibrido_brand_bible"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Adiciona tentativas_publicacao, atualizado_em e índice para recuperação de crash."""
    op.add_column(
        "postagens",
        sa.Column(
            "tentativas_publicacao",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "postagens",
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_posts_status_atualizado", "postagens", ["status", "atualizado_em"])


def downgrade() -> None:
    """Remove colunas e índice de resiliência do Worker em postagens."""
    op.drop_index("ix_posts_status_atualizado", table_name="postagens")
    op.drop_column("postagens", "atualizado_em")
    op.drop_column("postagens", "tentativas_publicacao")
