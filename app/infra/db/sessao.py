"""Configuração de Base Declarative, TypeDecorator UTC e fábrica de sessões Async."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import MetaData, text
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import DateTime, TypeDecorator

from app.core.config import Configuracoes

CONVENCAO_NOMES: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Classe base dos modelos SQLAlchemy com convenção de nomes estável."""

    metadata = MetaData(naming_convention=CONVENCAO_NOMES)


class DateTimeUTC(TypeDecorator[datetime]):
    """Garante datetimes timezone-aware em UTC no PostgreSQL e no SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def criar_engine_async(config: Configuracoes) -> AsyncEngine:
    """Constrói AsyncEngine com pool em PostgreSQL e conexão simples em SQLite."""
    url = config.resolver_database_url()
    if url.startswith("sqlite"):
        return create_async_engine(url, echo=config.db_echo)
    return create_async_engine(
        url,
        echo=config.db_echo,
        pool_size=config.db_pool_size,
        max_overflow=config.db_max_overflow,
        pool_pre_ping=True,
    )


def criar_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Cria fábrica de AsyncSession isolada por operação/requisição."""
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def verificar_saude_banco(engine: AsyncEngine) -> bool:
    """Executa SELECT 1 para readiness checks do Docker/Caddy."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True
