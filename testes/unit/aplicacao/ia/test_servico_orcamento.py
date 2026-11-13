"""Testes unitários do BudgetGuard, estimativas e contabilização mensal USD."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.aplicacao.ia.servico_orcamento import (
    ServicoOrcamentoUseCase,
    estimar_chamada,
    estimar_plano_semanal,
)
from app.dominio.entidades.ia_rag import RegistroCustoIA
from app.dominio.entidades.tenant import Empresa
from app.dominio.excecoes import ErroOrcamentoExcedido
from app.infra.memoria.repo_publicacao_mem import InMemoryCustoRepository
from app.infra.memoria.repo_tenant_mem import InMemoryEmpresaRepository


async def test_modo_estrito_bloqueia_e_modo_economico_forca_free() -> None:
    emp_repo = InMemoryEmpresaRepository()
    custo_repo = InMemoryCustoRepository()
    agora = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

    emp_estrita = Empresa(
        nome="Estrita", limite_mensal_usd=Decimal("0.0500"), bloqueio_orcamento=True
    )
    emp_econ = Empresa(
        nome="Economica", limite_mensal_usd=Decimal("0.0500"), bloqueio_orcamento=False
    )
    await emp_repo.salvar(emp_estrita)
    await emp_repo.salvar(emp_econ)

    conta_id = uuid4()
    for emp in (emp_estrita, emp_econ):
        await custo_repo.registrar(
            RegistroCustoIA(
                empresa_id=emp.id,
                conta_ig_id=conta_id,
                openrouter_gen_id="g-ini",
                modelo="google/gemini-3.1-flash-image",
                tokens_in=50,
                tokens_out=1000,
                custo_usd=Decimal("0.0500"),
                criado_em=agora,
            )
        )

    uc = ServicoOrcamentoUseCase(emp_repo, custo_repo, relogio=lambda: agora)
    assert await uc.verificar_disponibilidade(emp_estrita.id, Decimal("0.001")) is False

    with pytest.raises(ErroOrcamentoExcedido):
        await uc.decidir_politica_chamada(
            emp_estrita.id, "deepseek/deepseek-v4-flash", Decimal("0.002")
        )

    decisao_txt = await uc.decidir_politica_chamada(
        emp_econ.id, "deepseek/deepseek-v4-flash", Decimal("0.002"), exige_imagem_paga=False
    )
    assert decisao_txt.modo_economico_ativado is True
    assert decisao_txt.modelo_efetivo == "openrouter/free"

    with pytest.raises(ErroOrcamentoExcedido):
        await uc.decidir_politica_chamada(
            emp_econ.id, "google/gemini-3.1-flash-image", Decimal("0.045"), exige_imagem_paga=True
        )


async def test_estimativa_registro_e_resumo_mensal_por_conta() -> None:
    emp_repo = InMemoryEmpresaRepository()
    custo_repo = InMemoryCustoRepository()
    agora = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    emp = await emp_repo.salvar(Empresa(nome="Agencia", limite_mensal_usd=Decimal("10.00")))
    conta_a, conta_b = uuid4(), uuid4()

    uc = ServicoOrcamentoUseCase(emp_repo, custo_repo, relogio=lambda: agora)
    await uc.registrar_consumo(
        emp.id,
        conta_a,
        {"openrouter_gen_id": "g1", "modelo": "deepseek", "tokens_in": 100, "tokens_out": 50,
         "custo_usd": Decimal("0.250000")},
    )
    await uc.registrar_consumo(
        emp.id,
        conta_b,
        {"openrouter_gen_id": "g2", "modelo": "deepseek", "tokens_in": 100, "tokens_out": 50,
         "custo_usd": Decimal("0.750000")},
    )

    resumo = await uc.obter_resumo_mensal(emp.id, conta_a)
    assert resumo.gasto_empresa_usd == Decimal("1.000000")
    assert resumo.gasto_conta_usd == Decimal("0.250000")
    assert resumo.saldo_disponivel_usd == Decimal("9.000000")
    assert resumo.percentual_usado == 10.0

    est = estimar_plano_semanal(
        [{"usar_ia_imagem": True}, {"usar_ia_imagem": False}],
        "deepseek/deepseek-v4-flash",
        "google/gemini-3.1-flash-image",
    )
    assert est == (estimar_chamada("deepseek/deepseek-v4-flash") * 2) + estimar_chamada(
        "google/gemini-3.1-flash-image", eh_imagem=True
    )
