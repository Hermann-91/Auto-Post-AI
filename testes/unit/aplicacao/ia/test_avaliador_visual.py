"""Testes unitários do Crítico Visual VLM (Scorecard JSON binário PASS/FAIL)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any

from PIL import Image

from app.aplicacao.ia.avaliador_visual import AvaliadorVisualCritico
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.excecoes import ErroIntegracaoIA
from app.infra.memoria.repo_publicacao_mem import InMemoryCustoRepository
from app.infra.memoria.repo_tenant_mem import InMemoryEmpresaRepository
from app.infra.midia.processador_imagem import ProcessadorImagem


def _img_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1400, 1400), (80, 120, 90)).save(buf, format="JPEG")
    return buf.getvalue()


class _FakeVisaoCritico:
    def __init__(self, resposta: str | None = None, falhar: bool = False) -> None:
        self._resposta = resposta
        self._falhar = falhar
        self.ultima_url = ""

    async def analisar_imagem(
        self, system_prompt: str, user_prompt: str, imagem_data_url: str, modelo: str
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt)
        self.ultima_url = imagem_data_url
        if self._falhar:
            raise ErroIntegracaoIA("Timeout VLM")
        return self._resposta or "{}", {
            "openrouter_gen_id": "crit-1", "modelo": modelo,
            "tokens_in": 200, "tokens_out": 40, "custo_usd": Decimal("0.0015"),
        }


async def test_critico_visual_pass_e_fail_por_criterio_booleano() -> None:
    emp_repo, custo_repo = InMemoryEmpresaRepository(), InMemoryCustoRepository()
    emp = await emp_repo.salvar(Empresa(nome="Clinica", limite_mensal_usd=Decimal("5.00")))
    conta = ContaInstagram(
        empresa_id=emp.id, ig_user_id="1", username="clinica_real",
        access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    visao_pass = _FakeVisaoCritico(json.dumps({
        "anatomia_correta": True, "sem_texto_corrompido": True,
        "realismo_fotografico": True, "aderencia_ao_briefing": True,
        "aprovado": True, "diagnostico_correcao": "",
    }))
    avaliador = AvaliadorVisualCritico(visao_pass, orc, ProcessadorImagem.compactar_entrada)
    v_pass = await avaliador.avaliar_imagem(emp.id, conta.id, _img_bytes(), "Médica em consulta")
    assert v_pass.aprovado is True and v_pass.custo_usd == Decimal("0.0015")
    assert visao_pass.ultima_url.startswith("data:image/jpeg;base64,")

    visao_fail = _FakeVisaoCritico(json.dumps({
        "anatomia_correta": False, "sem_texto_corrompido": True,
        "realismo_fotografico": True, "aderencia_ao_briefing": True,
        "aprovado": True,  # Mesmo se o modelo marcar True, criterio False deve reprovar
        "diagnostico_correcao": "Mão esquerda com seis dedos",
    }))
    avaliador_fail = AvaliadorVisualCritico(visao_fail, orc, ProcessadorImagem.compactar_entrada)
    v_fail = await avaliador_fail.avaliar_imagem(emp.id, conta.id, _img_bytes(), "Médica")
    assert v_fail.aprovado is False and "seis dedos" in v_fail.diagnostico_correcao


async def test_critico_visual_fallback_seguro_em_erro_ou_nao_json() -> None:
    emp_repo, custo_repo = InMemoryEmpresaRepository(), InMemoryCustoRepository()
    emp = await emp_repo.salvar(Empresa(nome="Loja", limite_mensal_usd=Decimal("5.00")))
    conta_id = emp.id
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)

    av_texto = AvaliadorVisualCritico(
        _FakeVisaoCritico("imagem boa sem json"), orc, ProcessadorImagem.compactar_entrada
    )
    v1 = await av_texto.avaliar_imagem(emp.id, conta_id, _img_bytes(), "Cena")
    assert v1.aprovado is True and v1.revisao_inconclusiva is True

    av_erro = AvaliadorVisualCritico(
        _FakeVisaoCritico(falhar=True), orc, ProcessadorImagem.compactar_entrada
    )
    v2 = await av_erro.avaliar_imagem(emp.id, conta_id, _img_bytes(), "Cena")
    assert v2.aprovado is True and v2.revisao_inconclusiva is True
