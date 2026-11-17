"""Modelos ORM para configuração IA, RAG, biblioteca de mídia, postagens e custos."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.sessao import Base, DateTimeUTC


class ConfigIAContaModel(Base):
    """Preferências de persona, templates e modelos por conta Instagram."""

    __tablename__ = "configs_ia_conta"
    __table_args__ = (
        UniqueConstraint("empresa_id", "conta_ig_id", name="uq_config_ia_empresa_conta"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    conta_ig_id: Mapped[UUID] = mapped_column(
        ForeignKey("contas_instagram.id", ondelete="CASCADE"), nullable=False
    )
    persona_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    templates_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    brand_bible_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    aplicar_logo_padrao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    modelo_texto_pref: Mapped[str] = mapped_column(String(160), nullable=False)
    modelo_img_pref: Mapped[str] = mapped_column(String(160), nullable=False)


class FonteRAGModel(Base):
    """Conhecimento indexado e segmentado em chunks por conta Instagram."""

    __tablename__ = "fontes_rag"
    __table_args__ = (Index("ix_fontes_rag_tenant_conta", "empresa_id", "conta_ig_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    conta_ig_id: Mapped[UUID] = mapped_column(
        ForeignKey("contas_instagram.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(32), nullable=False)
    titulo: Mapped[str] = mapped_column(String(240), nullable=False)
    conteudo_limpo: Mapped[str] = mapped_column(Text, nullable=False)
    chunks_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    resumo_fatos: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embeddings_chunks_json: Mapped[list[list[float]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    criado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)


class MidiaBibliotecaModel(Base):
    """Metadados de mídias na nuvem R2/S3 com controle de cota e curtidas."""

    __tablename__ = "midias_biblioteca"
    __table_args__ = (
        Index("ix_midias_tenant_conta_pasta", "empresa_id", "conta_ig_id", "pasta"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    conta_ig_id: Mapped[UUID] = mapped_column(
        ForeignKey("contas_instagram.id", ondelete="CASCADE"), nullable=False
    )
    pasta: Mapped[str] = mapped_column(String(32), nullable=False)
    chave_storage: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    tipo_arquivo: Mapped[str] = mapped_column(String(120), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    curtida_favorita: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resumo_visual: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)


class PlanejamentoSemanalModel(Base):
    """Grades semanais em duas etapas com cache de tendências e estimativa USD."""

    __tablename__ = "planejamentos_semanais"
    __table_args__ = (
        Index("ix_plan_tenant_conta_semana", "empresa_id", "conta_ig_id", "semana_inicio"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    conta_ig_id: Mapped[UUID] = mapped_column(
        ForeignKey("contas_instagram.id", ondelete="CASCADE"), nullable=False
    )
    semana_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    itens_grade_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    tendencias_cache_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    custo_estimado_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)


class PostagemModel(Base):
    """Postagens agendadas e publicadas com chave de idempotência Meta."""

    __tablename__ = "postagens"
    __table_args__ = (
        Index("ix_posts_tenant_conta_status", "empresa_id", "conta_ig_id", "status"),
        Index("ix_posts_agendado_status", "status", "agendado_para"),
        Index("ix_posts_status_atualizado", "status", "atualizado_em"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    conta_ig_id: Mapped[UUID] = mapped_column(
        ForeignKey("contas_instagram.id", ondelete="CASCADE"), nullable=False
    )
    planejamento_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("planejamentos_semanais.id", ondelete="SET NULL"), nullable=True
    )
    tipo_midia: Mapped[str] = mapped_column(String(32), nullable=False)
    midias_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    legenda: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    agendado_para: Mapped[datetime | None] = mapped_column(DateTimeUTC(), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    meta_container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    meta_media_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    erro_detalhe: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)
    tentativas_publicacao: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    atualizado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)


class RegistroCustoIAModel(Base):
    """Auditoria de tokens e custo real OpenRouter por empresa e conta."""

    __tablename__ = "registros_custo_ia"
    __table_args__ = (Index("ix_custos_empresa_criado", "empresa_id", "criado_em"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
    )
    conta_ig_id: Mapped[UUID] = mapped_column(
        ForeignKey("contas_instagram.id", ondelete="CASCADE"), nullable=False
    )
    postagem_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("postagens.id", ondelete="SET NULL"), nullable=True
    )
    openrouter_gen_id: Mapped[str] = mapped_column(String(160), nullable=False)
    modelo: Mapped[str] = mapped_column(String(160), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False)
    custo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)
