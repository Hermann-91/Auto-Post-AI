"""Comandos, DTOs e portas auxiliares da camada de aplicação de IA."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import PlanejamentoSemanal, Postagem
from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG, TipoMidia


class PipelineMidiaPort(Protocol):
    """Porta desacoplada para o pipeline determinístico de mídia (Fase 3)."""

    async def processar(
        self,
        tipo: TipoMidia,
        arquivos_bytes: list[bytes],
        parametros: dict[str, Any] | None = None,
    ) -> list[bytes]: ...


class CompactadorMiniaturaPort(Protocol):
    """Porta para compactação de miniatura antes do envio multimodal em base64."""

    def __call__(self, dados: bytes, max_lado: int = 1024, qualidade: int = 80) -> bytes: ...


@dataclass(frozen=True, slots=True)
class DecisaoOrcamentoDTO:
    """Resultado da validação prévia de orçamento (BudgetGuard)."""

    permitido: bool
    modelo_efetivo: str
    modo_economico_ativado: bool
    gasto_atual_usd: Decimal
    limite_mensal_usd: Decimal


@dataclass(frozen=True, slots=True)
class ResumoOrcamentoDTO:
    """Consolidação mensal de orçamento em USD da empresa e conta ativa."""

    empresa_id: UUID
    conta_ig_id: UUID | None
    ano: int
    mes: int
    limite_mensal_usd: Decimal
    gasto_empresa_usd: Decimal
    gasto_conta_usd: Decimal
    saldo_disponivel_usd: Decimal
    percentual_usado: float
    bloqueio_orcamento: bool


@dataclass(frozen=True, slots=True)
class AtualizarConfigIACmd:
    """Comando para configurar persona, templates e modelos por conta Instagram."""

    empresa_id: UUID
    conta_ig_id: UUID
    persona_json: dict[str, Any]
    templates_json: dict[str, Any]
    aplicar_logo_padrao: bool
    modelo_texto_pref: str
    modelo_img_pref: str


@dataclass(frozen=True, slots=True)
class IndexarFonteRagCmd:
    """Comando para limpar, segmentar e indexar conhecimento na base RAG da conta."""

    empresa_id: UUID
    conta_ig_id: UUID
    tipo: TipoFonteRAG
    titulo: str
    conteudo: str


@dataclass(frozen=True, slots=True)
class CriarConteudoCmd:
    """Entrada para geração assistida de conteúdo e mídia híbrida."""

    empresa_id: UUID
    conta_ig_id: UUID
    tipo_midia: TipoMidia
    tema: str
    objetivo: str = "engajamento"
    tom_extra: str = ""
    gerar_imagem_ia: bool = False
    editar_midia_id: UUID | None = None
    midia_base_ids: tuple[UUID, ...] = ()
    prompt_visual_extra: str = ""
    presets_melhoria: tuple[str, ...] = ()
    proporcao: str = "4:5"
    aplicar_logo: bool | None = None
    logo_bytes: bytes | None = None
    salvar_rascunho: bool = True
    planejamento_id: UUID | None = None
    modelo_texto: str | None = None
    modelo_imagem: str | None = None


@dataclass(frozen=True, slots=True)
class ConteudoGeradoDTO:
    """Saída consolidada da criação individual com ativos, post e custos reais."""

    legenda: str
    hashtags: list[str]
    prompt_visual: str
    roteiro_slides: list[str]
    midias_geradas: list[MidiaBiblioteca]
    postagem: Postagem | None
    custo_total_usd: Decimal
    modelos_usados: list[str]
    modo_economico_ativado: bool


@dataclass(frozen=True, slots=True)
class CuradoriaVisualDTO:
    """Resultado da análise visual econômica de uma mídia da biblioteca."""

    midia: MidiaBiblioteca
    resumo_visual: str
    custo_usd: Decimal
    modelo_usado: str


@dataclass(frozen=True, slots=True)
class ProporPlanejamentoCmd:
    """Entrada da Etapa 1 do Planejamento Semanal Automatizado."""

    empresa_id: UUID
    conta_ig_id: UUID
    semana_inicio: date
    nicho: str = ""
    regiao: str = ""
    objetivo_semana: str = "crescimento orgânico e autoridade"
    quantidade_posts: int = 5
    incluir_imagens_ia: bool = True
    ttl_tendencias_horas: int = 48
    midia_ids_anexadas: tuple[UUID, ...] = ()
    presets_melhoria: tuple[str, ...] = ()
    instrucao_melhoria: str = ""


@dataclass(frozen=True, slots=True)
class ResultadoExecucaoPlanoDTO:
    """Resumo da Etapa 2 após execução de grade semanal aprovada."""

    plano: PlanejamentoSemanal
    postagens_criadas: list[Postagem]
    falhas_itens: list[str]
    custo_real_usd: Decimal
