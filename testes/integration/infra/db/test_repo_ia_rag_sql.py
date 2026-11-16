"""Testes de integração dos repositórios SQL de ConfigIA, RAG e Planejamento."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Configuracoes
from app.dominio.entidades.ia_rag import FonteRAG
from app.dominio.entidades.publicacao import PlanejamentoSemanal
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG
from app.infra.db.repo_conta_ig_sql import SqlContaIGRepository
from app.infra.db.repo_ia_rag_sql import (
    SqlConfigIARepository,
    SqlPlanejamentoRepository,
    SqlRagRepository,
)
from app.infra.db.repo_tenant_sql import SqlEmpresaRepository
from app.infra.db.sessao import Base, criar_engine_async, criar_session_factory


@pytest.fixture
async def ctx_ia(
    tmp_path: Path,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], UUID, UUID, UUID]]:
    cfg = Configuracoes(
        app_env="test",
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path}/ia_rag.db"),
    )
    engine = criar_engine_async(cfg)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = criar_session_factory(engine)
    emp = await SqlEmpresaRepository(sf).salvar(Empresa(nome="Agência IA"))
    exp = datetime.now(UTC) + timedelta(days=30)
    conta_a = await SqlContaIGRepository(sf).salvar(
        ContaInstagram(
            empresa_id=emp.id,
            ig_user_id="301",
            username="ia_a",
            access_token_enc="tok",
            token_expira_em=exp,
        )
    )
    conta_b = await SqlContaIGRepository(sf).salvar(
        ContaInstagram(
            empresa_id=emp.id,
            ig_user_id="302",
            username="ia_b",
            access_token_enc="tok",
            token_expira_em=exp,
        )
    )
    yield sf, emp.id, conta_a.id, conta_b.id
    await engine.dispose()


async def test_config_ia_rag_e_planejamento_por_conta(
    ctx_ia: tuple[async_sessionmaker[AsyncSession], UUID, UUID, UUID],
) -> None:
    sf, emp_id, conta_a, conta_b = ctx_ia
    cfg_repo = SqlConfigIARepository(sf)
    rag_repo = SqlRagRepository(sf)
    plan_repo = SqlPlanejamentoRepository(sf)

    padrao = await cfg_repo.obter_ou_padrao(emp_id, conta_a)
    assert padrao.aplicar_logo_padrao is False
    padrao.aplicar_logo_padrao = True
    padrao.persona_json = {"tom": "tecnico"}
    padrao.brand_bible_json = {"marca": "IA A", "nicho": "cafe"}
    await cfg_repo.salvar(padrao)
    lida = await cfg_repo.obter_ou_padrao(emp_id, conta_a)
    assert lida.aplicar_logo_padrao is True and lida.persona_json["tom"] == "tecnico"
    assert lida.brand_bible_json["nicho"] == "cafe"

    fonte = FonteRAG(
        empresa_id=emp_id,
        conta_ig_id=conta_a,
        tipo=TipoFonteRAG.URL,
        titulo="Horários",
        conteudo_limpo="Atendemos das 8h às 18h.",
        chunks=["Atendemos das 8h às 18h."],
        resumo_fatos="Atendimento 8h-18h",
        embeddings_chunks=[[0.25, 0.75]],
    )
    await rag_repo.salvar(fonte)
    salvas = await rag_repo.listar_por_conta(emp_id, conta_a)
    assert len(salvas) == 1
    assert salvas[0].resumo_fatos == "Atendimento 8h-18h"
    assert salvas[0].embeddings_chunks == [[0.25, 0.75]]
    assert len(await rag_repo.listar_por_conta(emp_id, conta_b)) == 0
    assert await rag_repo.remover(emp_id, conta_b, fonte.id) is False
    assert await rag_repo.remover(emp_id, conta_a, fonte.id) is True
    assert await rag_repo.listar_por_conta(emp_id, conta_a) == []

    plano = PlanejamentoSemanal(
        empresa_id=emp_id,
        conta_ig_id=conta_a,
        semana_inicio=date(2026, 11, 16),
        itens_grade=[{"dia": "seg", "tema": "Bastidores"}],
        custo_estimado_usd=Decimal("0.0450"),
    )
    plano.enviar_para_aprovacao()
    plano.aprovar()
    await plan_repo.salvar(plano)
    lido = await plan_repo.buscar_por_id(emp_id, conta_a, plano.id)
    assert lido is not None and lido.custo_estimado_usd == Decimal("0.0450")
    assert await plan_repo.buscar_por_id(emp_id, conta_b, plano.id) is None
    assert len(await plan_repo.listar_por_conta(emp_id, conta_a)) == 1
    assert await plan_repo.listar_por_conta(emp_id, conta_b) == []
