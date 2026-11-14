"""Schemas Pydantic para configuração IA/RAG, orçamento, criação e planejamento."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.dominio.objetos_valor.enums_conteudo import (
    PastaMidia,
    StatusPlanejamento,
    StatusPostagem,
    TipoFonteRAG,
    TipoMidia,
)
from app.dominio.objetos_valor.enums_tenant import ProvedorMeta


class ContaInstagramResumoResponse(BaseModel):
    id: UUID
    ig_user_id: str
    username: str
    provedor: ProvedorMeta
    ativa: bool


class SalvarContaInstagramRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conta_id: UUID | None = None
    username: str = Field(min_length=1, max_length=80)
    ig_user_id: str = Field(default="", max_length=80)
    access_token: str = Field(default="", max_length=2048)
    modo_sandbox: bool = False
    validade_dias: int = Field(default=60, ge=1, le=365)


class AtualizarConfigIARequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona_json: dict[str, Any] = Field(default_factory=dict)
    templates_json: dict[str, Any] = Field(default_factory=dict)
    aplicar_logo_padrao: bool = False
    modelo_texto_pref: str = Field(
        default="deepseek/deepseek-v4-flash", min_length=3, max_length=160
    )
    modelo_img_pref: str = Field(
        default="google/gemini-3.1-flash-image", min_length=3, max_length=160
    )


class ConfigIAResponse(BaseModel):
    id: UUID
    empresa_id: UUID
    conta_ig_id: UUID
    persona_json: dict[str, Any]
    templates_json: dict[str, Any]
    aplicar_logo_padrao: bool
    modelo_texto_pref: str
    modelo_img_pref: str


class IndexarFonteRagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoFonteRAG
    titulo: str = Field(min_length=2, max_length=240)
    conteudo: str = Field(min_length=5, max_length=50000)


class FonteRagResponse(BaseModel):
    id: UUID
    conta_ig_id: UUID
    tipo: TipoFonteRAG
    titulo: str
    total_chunks: int
    chunks: list[str]
    criado_em: datetime


class ResumoOrcamentoResponse(BaseModel):
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


class CriarConteudoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conta_ig_id: UUID
    tipo_midia: TipoMidia
    tema: str = Field(min_length=2, max_length=400)
    objetivo: str = Field(default="engajamento", min_length=2, max_length=200)
    tom_extra: str = Field(default="", max_length=200)
    gerar_imagem_ia: bool = False
    editar_midia_id: UUID | None = None
    midia_base_ids: list[UUID] = Field(default_factory=list, max_length=10)
    prompt_visual_extra: str = Field(default="", max_length=500)
    proporcao: str = Field(default="4:5", max_length=10)
    aplicar_logo: bool | None = None
    salvar_rascunho: bool = True
    modelo_texto: str | None = Field(default=None, max_length=160)
    modelo_imagem: str | None = Field(default=None, max_length=160)


class MidiaResumoResponse(BaseModel):
    id: UUID
    pasta: PastaMidia
    chave_storage: str
    tipo_arquivo: str
    tamanho_bytes: int
    curtida_favorita: bool
    resumo_visual: str


class PostagemResumoResponse(BaseModel):
    id: UUID
    conta_ig_id: UUID
    tipo_midia: TipoMidia
    midias_chaves: list[str]
    legenda: str
    status: StatusPostagem
    planejamento_id: UUID | None


class CriarConteudoResponse(BaseModel):
    legenda: str
    hashtags: list[str]
    prompt_visual: str
    roteiro_slides: list[str]
    midias_geradas: list[MidiaResumoResponse]
    postagem: PostagemResumoResponse | None
    custo_total_usd: Decimal
    modelos_usados: list[str]
    modo_economico_ativado: bool


class CuradoriaVisualResponse(BaseModel):
    midia_id: UUID
    resumo_visual: str
    custo_usd: Decimal
    modelo_usado: str


class ProporPlanejamentoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conta_ig_id: UUID
    semana_inicio: date
    nicho: str = Field(default="", max_length=160)
    regiao: str = Field(default="", max_length=120)
    objetivo_semana: str = Field(
        default="crescimento orgânico e autoridade", max_length=300
    )
    quantidade_posts: int = Field(default=5, ge=1, le=14)
    incluir_imagens_ia: bool = True
    ttl_tendencias_horas: int = Field(default=48, ge=24, le=72)


class PlanejamentoResponse(BaseModel):
    id: UUID
    conta_ig_id: UUID
    semana_inicio: date
    status: StatusPlanejamento
    custo_estimado_usd: Decimal
    itens_grade: list[dict[str, Any]]
    tendencias_cache: dict[str, Any]
    criado_em: datetime


class ExecucaoPlanejamentoResponse(BaseModel):
    plano: PlanejamentoResponse
    postagens_criadas: list[PostagemResumoResponse]
    falhas_itens: list[str]
    custo_real_usd: Decimal
