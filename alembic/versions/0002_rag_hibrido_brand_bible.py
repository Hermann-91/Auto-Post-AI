"""Adiciona Brand Bible, resumo factual e embeddings ao RAG.

Revision ID: 0002_rag_hibrido_brand_bible
Revises: 0001_estrutura_inicial
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_rag_hibrido_brand_bible"
down_revision: str | Sequence[str] | None = "0001_estrutura_inicial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Adiciona colunas de Brand Bible e RAG híbrido preservando dados existentes."""
    op.add_column(
        "configs_ia_conta",
        sa.Column(
            "brand_bible_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "fontes_rag",
        sa.Column(
            "resumo_fatos",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "fontes_rag",
        sa.Column(
            "embeddings_chunks_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    """Remove colunas adicionadas para RAG híbrido e Brand Bible."""
    op.drop_column("fontes_rag", "embeddings_chunks_json")
    op.drop_column("fontes_rag", "resumo_fatos")
    op.drop_column("configs_ia_conta", "brand_bible_json")
