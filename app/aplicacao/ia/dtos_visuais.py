"""DTOs do Pipeline Visual: Diretor de Arte, Crítico VLM e Loop de Revisão."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.dominio.entidades.midia import MidiaBiblioteca


@dataclass(frozen=True, slots=True)
class SceneSpec:
    """Especificação fotográfica documental estruturada produzida pelo Diretor de Arte."""

    sujeito_principal: str
    acao_e_narrativa: str
    ambiente: str
    enquadramento_lente: str
    iluminacao: str
    paleta_e_clima: str
    evitar: tuple[str, ...] = ()
    prompt_imagem_final: str = ""
    modo_serie: bool = False
    etapa_serie: str = ""
    pilar_editorial: str = ""

    def resumo_anti_repeticao(self) -> str:
        """Gera descrição enxuta da cena para memória anti-repetição da conta."""
        partes = [self.sujeito_principal, self.enquadramento_lente, self.iluminacao]
        texto = " | ".join(p.strip() for p in partes if p.strip())
        return texto[:280]

    def para_dict(self) -> dict[str, Any]:
        """Serializa SceneSpec para diagnóstico e auditoria."""
        return {
            "sujeito_principal": self.sujeito_principal,
            "acao_e_narrativa": self.acao_e_narrativa,
            "ambiente": self.ambiente,
            "enquadramento_lente": self.enquadramento_lente,
            "iluminacao": self.iluminacao,
            "paleta_e_clima": self.paleta_e_clima,
            "evitar": list(self.evitar),
            "prompt_imagem_final": self.prompt_imagem_final,
            "modo_serie": self.modo_serie,
            "etapa_serie": self.etapa_serie,
            "pilar_editorial": self.pilar_editorial,
        }


@dataclass(frozen=True, slots=True)
class VereditoCriticoVisual:
    """Scorecard binário PASS/FAIL produzido pelo Crítico Visual VLM."""

    anatomia_correta: bool
    sem_texto_corrompido: bool
    realismo_fotografico: bool
    aderencia_ao_briefing: bool
    aprovado: bool
    diagnostico_correcao: str = ""
    revisao_inconclusiva: bool = False
    custo_usd: Decimal = Decimal("0")
    modelo_usado: str = ""

    def para_dict(self) -> dict[str, Any]:
        """Serializa veredito para retorno da API e inspeção."""
        return {
            "anatomia_correta": self.anatomia_correta,
            "sem_texto_corrompido": self.sem_texto_corrompido,
            "realismo_fotografico": self.realismo_fotografico,
            "aderencia_ao_briefing": self.aderencia_ao_briefing,
            "aprovado": self.aprovado,
            "diagnostico_correcao": self.diagnostico_correcao,
            "revisao_inconclusiva": self.revisao_inconclusiva,
            "modelo_usado": self.modelo_usado,
        }


@dataclass(frozen=True, slots=True)
class QualidadeRevisaoVisual:
    """Resumo consolidado do loop de geração e crítica visual (até 2 iterações)."""

    aprovado: bool
    tentativas_geracao: int
    revisoes_critico: int
    ultimo_veredito: VereditoCriticoVisual | None = None
    historico_diagnosticos: tuple[str, ...] = ()
    modo_serie: bool = False
    etapa_serie: str = ""
    pilar_editorial: str = ""

    def para_dict(self) -> dict[str, Any]:
        """Serializa qualidade visual para ConteudoGeradoDTO."""
        return {
            "aprovado": self.aprovado,
            "status": "PASS" if self.aprovado else "FAIL",
            "tentativas_geracao": self.tentativas_geracao,
            "revisoes_critico": self.revisoes_critico,
            "ultimo_veredito": self.ultimo_veredito.para_dict() if self.ultimo_veredito else None,
            "historico_diagnosticos": list(self.historico_diagnosticos),
            "modo_serie": self.modo_serie,
            "etapa_serie": self.etapa_serie,
            "pilar_editorial": self.pilar_editorial,
        }


@dataclass(frozen=True, slots=True)
class ResultadoGeracaoVisual:
    """Saída completa do GeradorVisualHibrido com mídia, custos e revisão VLM."""

    midia: MidiaBiblioteca
    custo_total_usd: Decimal
    modelos_usados: list[str]
    qualidade_revisao: QualidadeRevisaoVisual
    prompt_final_usado: str
