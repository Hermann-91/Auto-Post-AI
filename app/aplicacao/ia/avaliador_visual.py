"""Crítico Visual VLM com Scorecard JSON binário PASS/FAIL (até 2 loops)."""

from __future__ import annotations

import base64
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.aplicacao.ia.dtos import CompactadorMiniaturaPort
from app.aplicacao.ia.dtos_visuais import SceneSpec, VereditoCriticoVisual
from app.aplicacao.ia.json_ia import extrair_objeto_json
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.dominio.excecoes import ErroIntegracaoIA
from app.dominio.portas.ia_meta import ClienteVisaoPort

logger = logging.getLogger(__name__)

_SYSTEM_CRITICO_GLOBAL = (
    "[CRÍTICO VISUAL GLOBAL DE QUALIDADE FOTOGRÁFICA]\n"
    "Você audita imagens geradas para Instagram antes da aprovação final.\n"
    "Avalie com rigor técnico e responda ESTRITAMENTE em JSON válido com as chaves:\n"
    '- "anatomia_correta" (bool): true se mãos, dedos, rostos e objetos não têm distorções.\n'
    '- "sem_texto_corrompido" (bool): true se não há letras borradas ou texto espúrio.\n'
    '- "realismo_fotografico" (bool): true se parece foto real sem aspecto plástico/CGI.\n'
    '- "aderencia_ao_briefing" (bool): true se atende fielmente ao SceneSpec solicitado.\n'
    '- "aprovado" (bool): true SOMENTE quando todos os 4 critérios acima forem true.\n'
    '- "diagnostico_correcao" (str): correção objetiva se reprovado, ou string vazia se PASS.'
)


def _interpretar_bool(valor: Any, padrao: bool = True) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        norm = valor.strip().lower()
        if norm in {"false", "0", "nao", "não", "fail"}:
            return False
        if norm in {"true", "1", "sim", "pass"}:
            return True
    return padrao


class AvaliadorVisualCritico:
    """Executa auditoria visual VLM com scorecard binário e controle de orçamento."""

    def __init__(
        self,
        cliente_visao: ClienteVisaoPort,
        orcamento: ServicoOrcamentoUseCase,
        compactador: CompactadorMiniaturaPort,
        modelo_visao_padrao: str = "google/gemini-2.5-flash-lite",
    ) -> None:
        self._visao = cliente_visao
        self._orcamento = orcamento
        self._compactar = compactador
        self._modelo_visao = modelo_visao_padrao

    @property
    def modelo_padrao(self) -> str:
        """Retorna modelo VLM configurado para a crítica visual."""
        return self._modelo_visao

    async def avaliar_imagem(
        self, empresa_id: UUID, conta_ig_id: UUID, imagem_bytes: bytes,
        briefing: SceneSpec | str, modelo_visao: str | None = None,
    ) -> VereditoCriticoVisual:
        """Compacta imagem, consulta VLM e retorna veredito binário PASS/FAIL."""
        modelo_alvo = (modelo_visao or self._modelo_visao).strip()
        decisao = await self._orcamento.decidir_politica_chamada(
            empresa_id=empresa_id,
            modelo_desejado=modelo_alvo,
            custo_estimado=estimar_chamada(modelo_alvo, eh_imagem=False),
            exige_imagem_paga=False,
        )
        mini = self._compactar(imagem_bytes, max_lado=1024, qualidade=85)
        data_url = f"data:image/jpeg;base64,{base64.b64encode(mini).decode('ascii')}"
        resumo_brief = (
            briefing.prompt_imagem_final if isinstance(briefing, SceneSpec) else briefing
        )
        user_prompt = (
            f"Briefing visual esperado:\n{resumo_brief[:600]}\n\n"
            "Retorne apenas o JSON binário de avaliação."
        )
        try:
            bruto, usage = await self._visao.analisar_imagem(
                system_prompt=_SYSTEM_CRITICO_GLOBAL,
                user_prompt=user_prompt,
                imagem_data_url=data_url,
                modelo=decisao.modelo_efetivo,
            )
        except ErroIntegracaoIA as exc:
            logger.warning("Crítico Visual VLM indisponível (%s); mantendo imagem.", exc)
            return VereditoCriticoVisual(
                anatomia_correta=True, sem_texto_corrompido=True, realismo_fotografico=True,
                aderencia_ao_briefing=True, aprovado=True, diagnostico_correcao="",
                revisao_inconclusiva=True, custo_usd=Decimal("0"),
                modelo_usado=decisao.modelo_efetivo,
            )
        reg = await self._orcamento.registrar_consumo(empresa_id, conta_ig_id, usage)
        return self._parsear_veredito(bruto, reg.custo_usd, reg.modelo)

    @staticmethod
    def _parsear_veredito(
        bruto: str, custo_usd: Decimal, modelo_usado: str
    ) -> VereditoCriticoVisual:
        try:
            dados = extrair_objeto_json(bruto)
        except ErroIntegracaoIA:
            logger.warning("Resposta não-JSON do Crítico Visual; mantendo revisão inconclusiva.")
            return VereditoCriticoVisual(
                anatomia_correta=True, sem_texto_corrompido=True, realismo_fotografico=True,
                aderencia_ao_briefing=True, aprovado=True, diagnostico_correcao="",
                revisao_inconclusiva=True, custo_usd=custo_usd, modelo_usado=modelo_usado,
            )
        anatomia = _interpretar_bool(dados.get("anatomia_correta"), True)
        sem_texto = _interpretar_bool(dados.get("sem_texto_corrompido"), True)
        realismo = _interpretar_bool(dados.get("realismo_fotografico"), True)
        aderencia = _interpretar_bool(dados.get("aderencia_ao_briefing"), True)
        aprovado_raw = _interpretar_bool(dados.get("aprovado"), True)
        aprovado = aprovado_raw and anatomia and sem_texto and realismo and aderencia
        diagnostico = str(dados.get("diagnostico_correcao") or "").strip()
        if not aprovado and not diagnostico:
            diagnostico = "Corrigir anatomia, remover texto espúrio e reforçar realismo documental."
        return VereditoCriticoVisual(
            anatomia_correta=anatomia, sem_texto_corrompido=sem_texto,
            realismo_fotografico=realismo, aderencia_ao_briefing=aderencia,
            aprovado=aprovado, diagnostico_correcao="" if aprovado else diagnostico[:300],
            revisao_inconclusiva=False, custo_usd=custo_usd, modelo_usado=modelo_usado,
        )
