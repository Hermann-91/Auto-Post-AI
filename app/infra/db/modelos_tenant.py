"""Modelos ORM para multi-tenancy, usuários, refresh tokens e contas Instagram."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.sessao import Base, DateTimeUTC


class EmpresaModel(Base):
    """Tabela raiz do tenant e limites comerciais/orçamentários."""

    __tablename__ = "empresas"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    plano: Mapped[str] = mapped_column(String(32), nullable=False)
    limite_mensal_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    bloqueio_orcamento: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)


class UsuarioModel(Base):
    """Usuários autenticáveis vinculados a uma única Empresa."""

    __tablename__ = "usuarios"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    papel: Mapped[str] = mapped_column(String(32), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)


class RefreshTokenModel(Base):
    """Estado de sessão para rotação segura e revogação por família de tokens."""

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    familia_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    substituido_por: Mapped[UUID | None] = mapped_column(nullable=True)
    revogado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expira_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)


class ContaInstagramModel(Base):
    """Contas Instagram gerenciadas pela Empresa com token OAuth criptografado."""

    __tablename__ = "contas_instagram"
    __table_args__ = (
        UniqueConstraint("empresa_id", "ig_user_id", name="uq_conta_ig_empresa_user"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    ig_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    token_expira_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)
    provedor: Mapped[str] = mapped_column(String(32), nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTimeUTC(), nullable=False)
