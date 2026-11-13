"""Schemas Pydantic para biblioteca de mídia, cotas, curtidas e limpeza."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.dominio.objetos_valor.enums_conteudo import PastaMidia


class MidiaBibliotecaResponse(BaseModel):
    """Representação de ativo da biblioteca acompanhado de URL pública."""

    id: UUID
    conta_ig_id: UUID
    pasta: PastaMidia
    chave_storage: str
    url_publica: str
    tipo_arquivo: str
    tamanho_bytes: int
    curtida_favorita: bool
    resumo_visual: str
    criado_em: datetime


class ResumoCotaResponse(BaseModel):
    """Consumo de itens e bytes da conta Instagram."""

    itens_usados: int
    max_itens: int
    percentual_itens: float
    bytes_usados: int
    max_bytes: int
    percentual_bytes: float


class AlternarCurtidaRequest(BaseModel):
    """Payload para marcar ou desmarcar mídia favorita."""

    favorita: bool


class ResultadoLimpezaResponse(BaseModel):
    """Resumo da limpeza pós-postagem preservando favoritas e filas ativas."""

    removidas_qtd: int
    bytes_liberados: int
    chaves_removidas: list[str]
    falhas: int
