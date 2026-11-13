"""Testes de integração do repositório SQL multi-conta Instagram."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Configuracoes
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.excecoes import ErroConflitoDados
from app.infra.db.repo_conta_ig_sql import SqlContaIGRepository
from app.infra.db.repo_tenant_sql import SqlEmpresaRepository
from app.infra.db.sessao import Base, criar_engine_async, criar_session_factory


@pytest.fixture
async def sf_conta(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    cfg = Configuracoes(
        app_env="test",
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path}/conta.db"),
    )
    engine = criar_engine_async(cfg)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield criar_session_factory(engine)
    await engine.dispose()


async def test_conta_ig_isolamento_upsert_e_unicidade(
    sf_conta: async_sessionmaker[AsyncSession],
) -> None:
    emp_repo = SqlEmpresaRepository(sf_conta)
    ig_repo = SqlContaIGRepository(sf_conta)

    emp1 = await emp_repo.salvar(Empresa(nome="Empresa 1"))
    emp2 = await emp_repo.salvar(Empresa(nome="Empresa 2"))

    conta = ContaInstagram(
        empresa_id=emp1.id,
        ig_user_id="17841",
        username="@loja",
        access_token_enc="enc_v1",
        token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    await ig_repo.salvar(conta)
    conta.atualizar_token("enc_v2", datetime.now(UTC) + timedelta(days=60))
    await ig_repo.salvar(conta)

    lida = await ig_repo.buscar_por_id(emp1.id, conta.id)
    assert lida is not None and lida.access_token_enc == "enc_v2"
    assert await ig_repo.buscar_por_id(emp2.id, conta.id) is None
    assert len(await ig_repo.listar_por_empresa(emp1.id)) == 1

    with pytest.raises(ErroConflitoDados):
        await ig_repo.salvar(
            ContaInstagram(
                empresa_id=emp1.id,
                ig_user_id="17841",
                username="outra",
                access_token_enc="enc",
                token_expira_em=datetime.now(UTC) + timedelta(days=10),
            )
        )

    encontrada = await ig_repo.buscar_por_ig_user_id(emp1.id, "17841")
    assert encontrada is not None and encontrada.id == conta.id
    assert await ig_repo.buscar_por_ig_user_id(emp2.id, "17841") is None

    conta_vencendo = ContaInstagram(
        empresa_id=emp2.id,
        ig_user_id="99900",
        username="expirando",
        access_token_enc="enc_exp",
        token_expira_em=datetime.now(UTC) + timedelta(days=3),
    )
    await ig_repo.salvar(conta_vencendo)
    renovaveis = await ig_repo.listar_para_renovacao_token(
        datetime.now(UTC) + timedelta(days=10)
    )
    assert [c.id for c in renovaveis] == [conta_vencendo.id]
