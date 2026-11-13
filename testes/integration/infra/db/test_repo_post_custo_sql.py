"""Testes de integração dos repositórios SQL de planejamento, postagens e custos."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Configuracoes
from app.dominio.entidades.ia_rag import RegistroCustoIA
from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.excecoes import ErroConflitoDados
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem, TipoMidia
from app.infra.db.repo_conta_ig_sql import SqlContaIGRepository
from app.infra.db.repo_post_custo_sql import (
    SqlCustoRepository,
    SqlPostagemRepository,
)
from app.infra.db.repo_tenant_sql import SqlEmpresaRepository
from app.infra.db.sessao import Base, criar_engine_async, criar_session_factory


@pytest.fixture
async def contexto_publicacao(
    tmp_path: Path,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], UUID, UUID]]:
    cfg = Configuracoes(
        app_env="test",
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path}/pub.db"),
    )
    engine = criar_engine_async(cfg)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = criar_session_factory(engine)
    emp = await SqlEmpresaRepository(sf).salvar(Empresa(nome="Publisher SA"))
    conta = await SqlContaIGRepository(sf).salvar(
        ContaInstagram(
            empresa_id=emp.id,
            ig_user_id="999",
            username="pub_ig",
            access_token_enc="tok",
            token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    yield sf, emp.id, conta.id
    await engine.dispose()


async def test_postagem_agendada_e_idempotencia(
    contexto_publicacao: tuple[async_sessionmaker[AsyncSession], UUID, UUID],
) -> None:
    sf, emp_id, conta_id = contexto_publicacao
    post_repo = SqlPostagemRepository(sf)

    agora = datetime(2026, 11, 13, 16, 0, tzinfo=UTC)
    p_vencida = Postagem(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        tipo_midia=TipoMidia.IMAGE,
        midias_chaves=["k1.jpg"],
        legenda="Post 1",
    )
    p_vencida.agendar(agora - timedelta(minutes=5))
    p_futura = Postagem(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        tipo_midia=TipoMidia.IMAGE,
        midias_chaves=["k2.jpg"],
        legenda="Post 2",
    )
    p_futura.agendar(agora + timedelta(hours=2))
    await post_repo.salvar(p_vencida)
    await post_repo.salvar(p_futura)

    pendentes = await post_repo.listar_agendadas_pendentes(agora)
    assert [p.id for p in pendentes] == [p_vencida.id]
    assert len(await post_repo.listar_por_conta(emp_id, conta_id, StatusPostagem.AGENDADO)) == 2

    with pytest.raises(ErroConflitoDados):
        await post_repo.salvar(
            Postagem(
                empresa_id=emp_id,
                conta_ig_id=conta_id,
                tipo_midia=TipoMidia.IMAGE,
                midias_chaves=["k3.jpg"],
                idempotency_key=p_vencida.idempotency_key,
            )
        )


async def test_custo_soma_mensal_inclusive_dezembro(
    contexto_publicacao: tuple[async_sessionmaker[AsyncSession], UUID, UUID],
) -> None:
    sf, emp_id, conta_id = contexto_publicacao
    repo = SqlCustoRepository(sf)

    await repo.registrar(
        RegistroCustoIA(
            empresa_id=emp_id,
            conta_ig_id=conta_id,
            openrouter_gen_id="g1",
            modelo="deepseek",
            tokens_in=100,
            tokens_out=50,
            custo_usd=Decimal("0.001250"),
            criado_em=datetime(2026, 12, 15, 10, 0, tzinfo=UTC),
        )
    )
    await repo.registrar(
        RegistroCustoIA(
            empresa_id=emp_id,
            conta_ig_id=conta_id,
            openrouter_gen_id="g2",
            modelo="nano-banana",
            tokens_in=100,
            tokens_out=0,
            custo_usd=Decimal("0.020000"),
            criado_em=datetime(2027, 1, 1, 0, 0, tzinfo=UTC),
        )
    )
    assert await repo.somar_mes_empresa(emp_id, 2026, 12) == Decimal("0.001250")
    assert await repo.somar_mes_empresa(emp_id, 2027, 1) == Decimal("0.020000")
    assert await repo.somar_mes_por_conta(emp_id, conta_id, 2026, 12) == Decimal("0.001250")
