"""Schemas Pydantic para criação e acompanhamento de jobs assíncronos de IA."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas.criacao_ia import CriarConteudoRequest, ProporPlanejamentoRequest
from app.dominio.entidades.job_ia import StatusJobIA, TipoJobIA


class ExecutarPlanoJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plano_id: UUID
    auto_agendar: bool | None = None
    fuso_horario: str | None = Field(default=None, max_length=64)


class RecriarPostagemJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    postagem_id: UUID
    alvo: str = Field(pattern="^(texto|imagem)$")
    contexto_adicional: str = Field(default="", max_length=800)
    presets_melhoria: list[str] = Field(default_factory=list, max_length=6)
    midia_base_id: UUID | None = None


class CriarJobIARequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conta_ig_id: UUID
    tipo_job: TipoJobIA
    chave_idempotencia: str = Field(default="", max_length=120)
    criar_conteudo: CriarConteudoRequest | None = None
    propor_plano: ProporPlanejamentoRequest | None = None
    executar_plano: ExecutarPlanoJobPayload | None = None
    recriar_postagem: RecriarPostagemJobPayload | None = None

    @model_validator(mode="after")
    def validar_payload_por_tipo(self) -> CriarJobIARequest:
        mapa: dict[TipoJobIA, object] = {
            TipoJobIA.CRIAR_CONTEUDO: self.criar_conteudo,
            TipoJobIA.PROPOR_PLANO: self.propor_plano,
            TipoJobIA.EXECUTAR_PLANO: self.executar_plano,
            TipoJobIA.RECRIAR_POSTAGEM: self.recriar_postagem,
        }
        alvo = mapa[self.tipo_job]
        if alvo is None:
            raise ValueError(f"Informe o bloco de parâmetros para o job '{self.tipo_job.value}'.")
        if self.criar_conteudo is not None and self.criar_conteudo.conta_ig_id != self.conta_ig_id:
            raise ValueError("conta_ig_id divergente entre job e criar_conteudo.")
        if self.propor_plano is not None and self.propor_plano.conta_ig_id != self.conta_ig_id:
            raise ValueError("conta_ig_id divergente entre job e propor_plano.")
        return self


class JobIAResponse(BaseModel):
    id: UUID
    conta_ig_id: UUID
    tipo_job: TipoJobIA
    status: StatusJobIA
    etapa_atual: str
    progresso_atual: int
    progresso_total: int
    percentual: int
    resultado_json: dict[str, Any] | None = None
    erro_detalhe: str | None = None
    criado_em: datetime
    atualizado_em: datetime
