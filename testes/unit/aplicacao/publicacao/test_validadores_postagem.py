"""Testes unitários de validadores_postagem.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.aplicacao.publicacao.dtos import CriarPostagemCmd
from app.aplicacao.publicacao.validadores_postagem import (
    exigir_conta_ativa,
    normalizar_agendamento_utc,
    resolver_chaves_midias,
)
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, TipoMidia
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryContaIGRepository,
    InMemoryMidiaRepository,
)


async def test_validadores_conta_midia_e_utc() -> None:
    conta_repo = InMemoryContaIGRepository()
    midia_repo = InMemoryMidiaRepository()
    emp = uuid4()
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp,
            ig_user_id="10",
            username="u10",
            access_token_enc="enc",
            token_expira_em=datetime.now(UTC) + timedelta(days=5),
        )
    )
    assert (await exigir_conta_ativa(conta_repo, emp, conta.id, True)).id == conta.id

    m = await midia_repo.salvar(
        MidiaBiblioteca(
            empresa_id=emp,
            conta_ig_id=conta.id,
            pasta=PastaMidia.ORIGINAIS,
            chave_storage="emp/c/originais/1.jpg",
            tipo_arquivo="image/jpeg",
            tamanho_bytes=100,
        )
    )
    cmd = CriarPostagemCmd(
        empresa_id=emp, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE, midia_ids=(m.id,)
    )
    assert await resolver_chaves_midias(midia_repo, cmd) == ["emp/c/originais/1.jpg"]

    with pytest.raises(ErroValidacaoDominio):
        normalizar_agendamento_utc(datetime(2026, 11, 20, 10, 0))
    assert normalizar_agendamento_utc(datetime(2026, 11, 20, 10, 0, tzinfo=UTC)).tzinfo == UTC
