"""Schemas Pydantic para contas Instagram, ConfigIA/Brand Bible, RAG e Orçamento."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG
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
    brand_bible_json: dict[str, Any] = Field(default_factory=dict)
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
    brand_bible_json: dict[str, Any]
    aplicar_logo_padrao: bool
    modelo_texto_pref: str
    modelo_img_pref: str


class CompilarBrandBibleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usar_ia: bool = False


class IndexarFonteRagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoFonteRAG
    titulo: str = Field(min_length=2, max_length=240)
    conteudo: str = Field(min_length=5, max_length=50000)


class IndexarUrlRagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=5, max_length=1000)
    tipo: TipoFonteRAG = TipoFonteRAG.URL
    titulo: str = Field(default="", max_length=240)


class FonteRagResponse(BaseModel):
    id: UUID
    conta_ig_id: UUID
    tipo: TipoFonteRAG
    titulo: str
    resumo_fatos: str
    tem_embeddings: bool
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
