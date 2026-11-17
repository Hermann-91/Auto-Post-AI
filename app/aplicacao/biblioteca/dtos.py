"""DTOs e comandos da camada de aplicação para biblioteca de mídia."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.objetos_valor.enums_conteudo import PastaMidia


@dataclass(frozen=True, slots=True)
class UploadMidiaCmd:
    """Entrada para registro de novo ativo respeitando cota e pasta."""

    empresa_id: UUID
    conta_ig_id: UUID
    pasta: PastaMidia
    nome_arquivo: str
    content_type: str
    conteudo: bytes
    resumo_visual: str = ""


@dataclass(frozen=True, slots=True)
class MidiaComUrlDTO:
    """Mídia persistida acompanhada da URL HTTPS pública."""

    midia: MidiaBiblioteca
    url_publica: str


@dataclass(frozen=True, slots=True)
class ResumoCotaDTO:
    """Visão consolidada do consumo de itens e bytes da conta."""

    itens_usados: int
    max_itens: int
    percentual_itens: float
    bytes_usados: int
    max_bytes: int
    percentual_bytes: float


@dataclass(frozen=True, slots=True)
class ResultadoLimpezaDTO:
    """Relatório da limpeza pós-postagem preservando favoritas e ativas."""

    removidas_qtd: int
    bytes_liberados: int
    chaves_removidas: list[str]
    falhas: int


@dataclass(frozen=True, slots=True)
class ResultadoExclusaoPostagemDTO:
    """Resumo da exclusão de postagem na Agenda e suas mídias órfãs."""

    postagem_id: UUID
    midias_removidas_qtd: int
    chaves_removidas: list[str]
    midias_preservadas_qtd: int


@dataclass(frozen=True, slots=True)
class ResultadoExclusaoMidiaDTO:
    """Resumo da exclusão direta de mídia na Biblioteca."""

    midia_id: UUID
    chave_storage: str
    bytes_liberados: int
