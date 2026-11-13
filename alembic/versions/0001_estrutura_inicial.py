"""Estrutura inicial multi-tenant e tabelas de conteúdo.

Revision ID: 0001_estrutura_inicial
Revises:
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_estrutura_inicial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fk(alvo: str, ondelete: str = "CASCADE") -> sa.ForeignKey:
    return sa.ForeignKey(alvo, ondelete=ondelete)


def upgrade() -> None:
    """Cria todas as tabelas e índices multi-tenant da aplicação."""
    op.create_table(
        "empresas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("plano", sa.String(length=32), nullable=False),
        sa.Column("limite_mensal_usd", sa.Numeric(12, 4), nullable=False),
        sa.Column("bloqueio_orcamento", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), _fk("empresas.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("senha_hash", sa.String(length=512), nullable=False),
        sa.Column("papel", sa.String(length=32), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_usuarios_email"),
    )
    op.create_index("ix_usuarios_empresa_id", "usuarios", ["empresa_id"])
    op.create_index("ix_usuarios_email", "usuarios", ["email"])
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), _fk("usuarios.id"), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), _fk("empresas.id"), nullable=False),
        sa.Column("familia_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("substituido_por", sa.Uuid(), nullable=True),
        sa.Column("revogado", sa.Boolean(), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_usuario_id", "refresh_tokens", ["usuario_id"])
    op.create_index("ix_refresh_tokens_empresa_id", "refresh_tokens", ["empresa_id"])
    op.create_index("ix_refresh_tokens_familia_id", "refresh_tokens", ["familia_id"])
    op.create_table(
        "contas_instagram",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), _fk("empresas.id"), nullable=False),
        sa.Column("ig_user_id", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("token_expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provedor", sa.String(length=32), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("empresa_id", "ig_user_id", name="uq_conta_ig_empresa_user"),
    )
    op.create_index("ix_contas_instagram_empresa_id", "contas_instagram", ["empresa_id"])
    op.create_table(
        "configs_ia_conta",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), _fk("empresas.id"), nullable=False),
        sa.Column("conta_ig_id", sa.Uuid(), _fk("contas_instagram.id"), nullable=False),
        sa.Column("persona_json", sa.JSON(), nullable=False),
        sa.Column("templates_json", sa.JSON(), nullable=False),
        sa.Column("aplicar_logo_padrao", sa.Boolean(), nullable=False),
        sa.Column("modelo_texto_pref", sa.String(length=160), nullable=False),
        sa.Column("modelo_img_pref", sa.String(length=160), nullable=False),
        sa.UniqueConstraint("empresa_id", "conta_ig_id", name="uq_config_ia_empresa_conta"),
    )
    op.create_table(
        "fontes_rag",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), _fk("empresas.id"), nullable=False),
        sa.Column("conta_ig_id", sa.Uuid(), _fk("contas_instagram.id"), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("titulo", sa.String(length=240), nullable=False),
        sa.Column("conteudo_limpo", sa.Text(), nullable=False),
        sa.Column("chunks_json", sa.JSON(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fontes_rag_tenant_conta", "fontes_rag", ["empresa_id", "conta_ig_id"])
    op.create_table(
        "midias_biblioteca",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), _fk("empresas.id"), nullable=False),
        sa.Column("conta_ig_id", sa.Uuid(), _fk("contas_instagram.id"), nullable=False),
        sa.Column("pasta", sa.String(length=32), nullable=False),
        sa.Column("chave_storage", sa.String(length=512), nullable=False),
        sa.Column("tipo_arquivo", sa.String(length=120), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=False),
        sa.Column("curtida_favorita", sa.Boolean(), nullable=False),
        sa.Column("resumo_visual", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("chave_storage", name="uq_midias_biblioteca_chave_storage"),
    )
    op.create_index(
        "ix_midias_tenant_conta_pasta",
        "midias_biblioteca",
        ["empresa_id", "conta_ig_id", "pasta"],
    )
    op.create_table(
        "planejamentos_semanais",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), _fk("empresas.id"), nullable=False),
        sa.Column("conta_ig_id", sa.Uuid(), _fk("contas_instagram.id"), nullable=False),
        sa.Column("semana_inicio", sa.Date(), nullable=False),
        sa.Column("itens_grade_json", sa.JSON(), nullable=False),
        sa.Column("tendencias_cache_json", sa.JSON(), nullable=False),
        sa.Column("custo_estimado_usd", sa.Numeric(12, 4), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_plan_tenant_conta_semana",
        "planejamentos_semanais",
        ["empresa_id", "conta_ig_id", "semana_inicio"],
    )
    op.create_table(
        "postagens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), _fk("empresas.id"), nullable=False),
        sa.Column("conta_ig_id", sa.Uuid(), _fk("contas_instagram.id"), nullable=False),
        sa.Column(
            "planejamento_id",
            sa.Uuid(),
            _fk("planejamentos_semanais.id", "SET NULL"),
            nullable=True,
        ),
        sa.Column("tipo_midia", sa.String(length=32), nullable=False),
        sa.Column("midias_json", sa.JSON(), nullable=False),
        sa.Column("legenda", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("agendado_para", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("meta_container_id", sa.String(length=128), nullable=True),
        sa.Column("meta_media_id", sa.String(length=128), nullable=True),
        sa.Column("erro_detalhe", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_postagens_idempotency_key"),
    )
    op.create_index(
        "ix_posts_tenant_conta_status",
        "postagens",
        ["empresa_id", "conta_ig_id", "status"],
    )
    op.create_index("ix_posts_agendado_status", "postagens", ["status", "agendado_para"])
    op.create_table(
        "registros_custo_ia",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), _fk("empresas.id"), nullable=False),
        sa.Column("conta_ig_id", sa.Uuid(), _fk("contas_instagram.id"), nullable=False),
        sa.Column("postagem_id", sa.Uuid(), _fk("postagens.id", "SET NULL"), nullable=True),
        sa.Column("openrouter_gen_id", sa.String(length=160), nullable=False),
        sa.Column("modelo", sa.String(length=160), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("custo_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_custos_empresa_criado", "registros_custo_ia", ["empresa_id", "criado_em"])


def downgrade() -> None:
    """Reverte a criação das tabelas na ordem inversa de dependências."""
    for tabela in (
        "registros_custo_ia",
        "postagens",
        "planejamentos_semanais",
        "midias_biblioteca",
        "fontes_rag",
        "configs_ia_conta",
        "contas_instagram",
        "refresh_tokens",
        "usuarios",
        "empresas",
    ):
        op.drop_table(tabela)
