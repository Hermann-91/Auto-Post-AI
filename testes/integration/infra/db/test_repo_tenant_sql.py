"""Testes de integração dos repositórios SQL de tenant e fluxo HTTP /auth com DB real."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Configuracoes
from app.dominio.entidades.tenant import Empresa, RefreshTokenRegistro, Usuario
from app.dominio.excecoes import ErroConflitoDados
from app.infra.db.repo_tenant_sql import (
    SqlEmpresaRepository,
    SqlRefreshTokenRepository,
    SqlUsuarioRepository,
)
from app.infra.db.sessao import Base, criar_engine_async, criar_session_factory
from app.main import criar_app


@pytest.fixture
async def session_factory_sql(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    cfg = Configuracoes(
        app_env="test",
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path}/tenant.db"),
    )
    engine = criar_engine_async(cfg)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield criar_session_factory(engine)
    await engine.dispose()


async def test_repos_empresa_usuario_e_conflito_email(
    session_factory_sql: async_sessionmaker[AsyncSession],
) -> None:
    emp_repo = SqlEmpresaRepository(session_factory_sql)
    usr_repo = SqlUsuarioRepository(session_factory_sql)

    emp = Empresa(nome="Agência Alfa")
    await emp_repo.salvar(emp)
    assert (await emp_repo.buscar_por_id(emp.id)) is not None

    usr = Usuario(empresa_id=emp.id, email="Admin@Alfa.com", senha_hash="hash_argon2")
    await usr_repo.salvar(usr)
    encontrado = await usr_repo.buscar_por_email("admin@alfa.com")
    assert encontrado is not None and encontrado.id == usr.id
    assert await usr_repo.buscar_por_id(uuid4(), usr.id) is None

    duplicado = Usuario(empresa_id=emp.id, email="admin@alfa.com", senha_hash="outro")
    with pytest.raises(ErroConflitoDados):
        await usr_repo.salvar(duplicado)


async def test_refresh_token_rotacao_e_revogacao_familia(
    session_factory_sql: async_sessionmaker[AsyncSession],
) -> None:
    emp_repo = SqlEmpresaRepository(session_factory_sql)
    usr_repo = SqlUsuarioRepository(session_factory_sql)
    ref_repo = SqlRefreshTokenRepository(session_factory_sql)

    emp = await emp_repo.salvar(Empresa(nome="Sessão Ltda"))
    usr = await usr_repo.salvar(Usuario(empresa_id=emp.id, email="u@s.com", senha_hash="h"))

    fam = uuid4()
    exp = datetime.now(UTC) + timedelta(days=7)
    t1 = RefreshTokenRegistro(
        usuario_id=usr.id,
        empresa_id=emp.id,
        familia_id=fam,
        token_hash="hash_1",
        expira_em=exp,
    )
    t2 = RefreshTokenRegistro(
        usuario_id=usr.id,
        empresa_id=emp.id,
        familia_id=fam,
        token_hash="hash_2",
        expira_em=exp,
    )
    await ref_repo.salvar(t1)
    await ref_repo.salvar(t2)
    await ref_repo.marcar_substituido(t1.id, t2.id)

    lido1 = await ref_repo.buscar_por_hash("hash_1")
    assert lido1 is not None and lido1.substituido_por == t2.id and not lido1.esta_valido()

    await ref_repo.revogar_familia(fam)
    lido2 = await ref_repo.buscar_por_hash("hash_2")
    assert lido2 is not None and lido2.revogado and not lido2.esta_valido()


async def test_api_auth_e_readyz_integrados_com_sqlalchemy(tmp_path: Path) -> None:
    cfg = Configuracoes(
        app_env="test",
        cors_origens=["https://painel.exemplo.com"],
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path}/api_sql.db"),
    )
    app = criar_app(cfg)
    engine = app.state.auth_container.db_engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as cli:
            ready = await cli.get("/readyz")
            assert ready.status_code == 200
            reg = await cli.post(
                "/auth/register",
                json={"nome_empresa": "SQL Co", "email": "sql@co.com", "senha": "SenhaForte#1"},
            )
            assert reg.status_code == 201
            assert (await cli.post("/auth/refresh")).status_code == 200
            assert (await cli.get("/auth/me")).json()["email"] == "sql@co.com"
    finally:
        await app.state.auth_container.fechar()
