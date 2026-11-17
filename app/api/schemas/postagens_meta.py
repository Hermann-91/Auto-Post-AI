"""Schemas Pydantic para OAuth Meta e agendamento/publicação de postagens."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.dominio.objetos_valor.enums_conteudo import StatusPostagem, TipoMidia
from app.dominio.objetos_valor.enums_tenant import ProvedorMeta


class UrlOAuthMetaResponse(BaseModel):
    url_autorizacao: str
    state: str
    provedor: ProvedorMeta = ProvedorMeta.INSTAGRAM_LOGIN


class ContaMetaConectadaResponse(BaseModel):
    id: UUID
    empresa_id: UUID
    ig_user_id: str
    username: str
    provedor: ProvedorMeta
    ativa: bool
    token_expira_em: datetime


class CriarPostagemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conta_ig_id: UUID
    tipo_midia: TipoMidia
    midia_ids: list[UUID] = Field(default_factory=list, max_length=10)
    midias_chaves: list[str] = Field(default_factory=list, max_length=10)
    legenda: str = Field(default="", max_length=2200)
    agendado_para: datetime | None = None
    planejamento_id: UUID | None = None


class AgendarPostagemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agendado_para: datetime


class RecriarPostagemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alvo: str = Field(pattern="^(texto|imagem)$")
    contexto_adicional: str = Field(default="", max_length=800)
    presets_melhoria: list[str] = Field(default_factory=list, max_length=6)
    midia_base_id: UUID | None = None


class SubstituirMidiaPostagemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nova_midia_id: UUID


class PostagemDetalheResponse(BaseModel):
    id: UUID
    conta_ig_id: UUID
    tipo_midia: TipoMidia
    midias_chaves: list[str]
    legenda: str
    status: StatusPostagem
    planejamento_id: UUID | None
    agendado_para: datetime | None
    meta_container_id: str | None
    meta_media_id: str | None
    erro_detalhe: str | None
    criado_em: datetime


class ResultadoPublicacaoResponse(BaseModel):
    postagem: PostagemDetalheResponse
    publicada: bool
    reagendada: bool
    motivo: str


class ResultadoExclusaoPostagemResponse(BaseModel):
    """Resumo da exclusão de postagem da Agenda e remoção de mídias exclusivas."""

    postagem_id: UUID
    midias_removidas_qtd: int
    chaves_removidas: list[str]
    midias_preservadas_qtd: int
