"""Testes unitários da entidade JobIA e invariantes de progresso."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.dominio.entidades.job_ia import JobIA, StatusJobIA, TipoJobIA
from app.dominio.excecoes import ErroValidacaoDominio


def test_ciclo_de_vida_e_percentual_job_ia() -> None:
    job = JobIA(
        empresa_id=uuid4(),
        conta_ig_id=uuid4(),
        tipo_job=TipoJobIA.EXECUTAR_PLANO,
        progresso_total=4,
        chave_idempotencia="  exec-1  ",
    )
    assert job.chave_idempotencia == "exec-1"
    assert job.status == StatusJobIA.PENDENTE
    assert job.percentual == 0 and not job.finalizado

    job.iniciar("Processando item 1")
    assert job.status.value == "EXECUTANDO"
    job.avancar(2, "Item 2/4")
    assert job.progresso_atual == 2 and job.percentual == 50

    job.concluir({"ok": True})
    assert job.status.value == "CONCLUIDO"
    assert job.finalizado and job.percentual == 100
    assert job.resultado_json == {"ok": True}

    job.avancar(1, "Ignorado após conclusão")
    assert job.progresso_atual == 4


def test_job_ia_falha_e_validacoes_invariantes() -> None:
    with pytest.raises(ErroValidacaoDominio):
        JobIA(empresa_id=uuid4(), conta_ig_id=uuid4(), tipo_job=TipoJobIA.CRIAR_CONTEUDO,
              progresso_total=0)
    with pytest.raises(ErroValidacaoDominio):
        JobIA(empresa_id=uuid4(), conta_ig_id=uuid4(), tipo_job=TipoJobIA.CRIAR_CONTEUDO,
              progresso_atual=2, progresso_total=1)

    job = JobIA(empresa_id=uuid4(), conta_ig_id=uuid4(), tipo_job=TipoJobIA.RECRIAR_POSTAGEM)
    job.falhar("   ")
    assert job.status == StatusJobIA.FALHA and job.finalizado
    assert job.erro_detalhe == "Falha desconhecida no processamento."
