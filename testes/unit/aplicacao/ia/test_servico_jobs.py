"""Testes unitários do JobIAStore e isolamento/resiliência do ServicoJobsIAUseCase."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from app.aplicacao.ia.jobs_store import JobIAStore
from app.aplicacao.ia.servico_jobs import ServicoJobsIAUseCase
from app.dominio.entidades.job_ia import JobIA, StatusJobIA, TipoJobIA
from app.dominio.entidades.tenant import ContaInstagram


class _FakePromptsRag:
    def __init__(self, conta: ContaInstagram) -> None:
        self._conta = conta

    async def exigir_conta(self, empresa_id: UUID, conta_ig_id: UUID) -> ContaInstagram:
        if empresa_id != self._conta.empresa_id or conta_ig_id != self._conta.id:
            raise AssertionError("Conta inválida")
        return self._conta


class _FakeRecriarErroInterno:
    async def recriar_com_contexto(self, **_kwargs: Any) -> Any:
        raise RuntimeError("Segredo interno XYZ não pode vazar")


async def test_store_isolamento_poda_e_idempotencia() -> None:
    store = JobIAStore(max_itens=10)
    emp_a, emp_b = uuid4(), uuid4()
    conta_a = uuid4()

    ativo = JobIA(
        empresa_id=emp_a, conta_ig_id=conta_a, tipo_job=TipoJobIA.PROPOR_PLANO,
        status=StatusJobIA.EXECUTANDO, chave_idempotencia="btn-1",
    )
    await store.salvar(ativo)

    for idx in range(12):
        done = JobIA(empresa_id=emp_a, conta_ig_id=conta_a, tipo_job=TipoJobIA.CRIAR_CONTEUDO)
        done.concluir({"idx": idx})
        await store.salvar(done)

    assert await store.buscar_por_id(emp_b, ativo.id) is None
    assert await store.buscar_por_id(emp_a, ativo.id) is ativo
    dup = await store.buscar_ativo_idempotente(emp_a, conta_a, TipoJobIA.PROPOR_PLANO, "btn-1")
    assert dup is not None and dup.id == ativo.id
    ativos = await store.listar_por_conta(emp_a, conta_a, apenas_ativos=True)
    assert [j.id for j in ativos] == [ativo.id]


async def test_servico_jobs_mascara_erro_interno_inesperado() -> None:
    emp_id = uuid4()
    conta = ContaInstagram(
        empresa_id=emp_id, ig_user_id="10", username="loja",
        access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    store = JobIAStore()
    uc = ServicoJobsIAUseCase(
        store=store,
        prompts_rag=cast(Any, _FakePromptsRag(conta)),
        criar_conteudo=cast(Any, object()),
        planejamento=cast(Any, object()),
        edicao_orcamento=cast(Any, object()),
        recriar_post=cast(Any, _FakeRecriarErroInterno()),
    )
    job = await uc.criar_e_agendar(
        empresa_id=emp_id, conta_ig_id=conta.id, tipo_job=TipoJobIA.RECRIAR_POSTAGEM,
        cmd_ou_dados={"postagem_id": str(uuid4()), "alvo": "imagem"},
        chave_idempotencia="req-1",
    )
    for _ in range(30):
        await asyncio.sleep(0.01)
        atual = await uc.obter_job(emp_id, job.id)
        if atual and atual.finalizado:
            break
    final = await uc.obter_job(emp_id, job.id)
    assert final is not None and final.status == StatusJobIA.FALHA
    assert final.erro_detalhe == "Falha interna ao processar job de IA."
    assert "Segredo" not in final.erro_detalhe
