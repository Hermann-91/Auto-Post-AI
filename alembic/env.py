"""Ambiente de migrações Alembic compatível com SQLAlchemy Async."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import obter_configuracoes
from app.infra.db import modelos_conteudo as _modelos_conteudo  # noqa: F401
from app.infra.db import modelos_tenant as _modelos_tenant  # noqa: F401
from app.infra.db.sessao import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolver_url() -> str:
    url_config = config.get_main_option("sqlalchemy.url")
    if url_config:
        return url_config
    return obter_configuracoes().resolver_database_url()


def run_migrations_offline() -> None:
    """Executa geração SQL offline sem abrir conexão com o banco."""
    context.configure(
        url=_resolver_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _executar_em_conexao(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    secao = config.get_section(config.config_ini_section, {})
    secao["sqlalchemy.url"] = _resolver_url()
    connectable = async_engine_from_config(
        secao,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_executar_em_conexao)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Executa migrações online usando o driver async configurado."""
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
