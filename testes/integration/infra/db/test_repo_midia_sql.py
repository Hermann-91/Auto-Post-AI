"""Testes de integração dos repositórios SQL de mídia, config IA e RAG."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Configuracoes
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.objetos_valor.enums_conteudo import PastaMidia
from app.infra.db.repo_conta_ig_sql import SqlContaIGRepository
from app.infra.db.repo_midia_sql import SqlMidiaRepository
from app.infra.db.repo_tenant_sql import SqlEmpresaRepository
from app.infra.db.sessao import Base, criar_engine_async, criar_session_factory


@pytest.fixture
async def contexto_conta(
    tmp_path: Path,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], UUID, UUID, UUID]]:
    cfg = Configuracoes(
        app_env="test",
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path}/midia.db"),
    )
    engine = criar_engine_async(cfg)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = criar_session_factory(engine)
    emp = await SqlEmpresaRepository(sf).salvar(Empresa(nome="Studio Mídia"))
    exp = datetime.now(UTC) + timedelta(days=30)
    conta_a = await SqlContaIGRepository(sf).salvar(
        ContaInstagram(
            empresa_id=emp.id,
            ig_user_id="101",
            username="conta_a",
            access_token_enc="tok",
            token_expira_em=exp,
        )
    )
    conta_b = await SqlContaIGRepository(sf).salvar(
        ContaInstagram(
            empresa_id=emp.id,
            ig_user_id="202",
            username="conta_b",
            access_token_enc="tok",
            token_expira_em=exp,
        )
    )
    yield sf, emp.id, conta_a.id, conta_b.id
    await engine.dispose()


async def test_midia_crud_cota_filtro_pasta_e_isolamento(
    contexto_conta: tuple[async_sessionmaker[AsyncSession], UUID, UUID, UUID],
) -> None:
    sf, emp_id, conta_a, conta_b = contexto_conta
    repo = SqlMidiaRepository(sf)

    m1 = MidiaBiblioteca(
        empresa_id=emp_id,
        conta_ig_id=conta_a,
        pasta=PastaMidia.ORIGINAIS,
        chave_storage=f"{emp_id}/{conta_a}/originais/foto1.jpg",
        tipo_arquivo="image/jpeg",
        tamanho_bytes=1200,
    )
    m2 = MidiaBiblioteca(
        empresa_id=emp_id,
        conta_ig_id=conta_a,
        pasta=PastaMidia.IA_CRIA,
        chave_storage=f"{emp_id}/{conta_a}/IA-Cria/arte.jpg",
        tipo_arquivo="image/jpeg",
        tamanho_bytes=2800,
        curtida_favorita=True,
    )
    m_b = MidiaBiblioteca(
        empresa_id=emp_id,
        conta_ig_id=conta_b,
        pasta=PastaMidia.ORIGINAIS,
        chave_storage=f"{emp_id}/{conta_b}/originais/outra.jpg",
        tipo_arquivo="image/jpeg",
        tamanho_bytes=9999,
    )
    await repo.salvar(m1)
    await repo.salvar(m2)
    await repo.salvar(m_b)

    assert await repo.calcular_uso_cota(emp_id, conta_a) == (2, 4000)
    assert len(await repo.listar_por_conta(emp_id, conta_a, PastaMidia.IA_CRIA)) == 1
    assert await repo.buscar_por_id(emp_id, conta_b, m1.id) is None

    m1.alternar_curtida(True)
    await repo.salvar(m1)
    atualizada = await repo.buscar_por_id(emp_id, conta_a, m1.id)
    assert atualizada is not None and atualizada.curtida_favorita is True

    await repo.remover(uuid4(), conta_a, m1.id)
    assert (await repo.calcular_uso_cota(emp_id, conta_a))[0] == 2
    await repo.remover(emp_id, conta_a, m1.id)
    assert await repo.calcular_uso_cota(emp_id, conta_a) == (1, 2800)
