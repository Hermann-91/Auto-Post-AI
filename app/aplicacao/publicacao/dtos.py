"""DTOs e comandos da camada de aplicação de publicação oficial e OAuth Meta."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.dominio.entidades.publicacao import Postagem
from app.dominio.objetos_valor.enums_conteudo import TipoMidia


@dataclass(frozen=True, slots=True)
class ConectarMetaCallbackCmd:
    """Comando para finalizar o fluxo OAuth Instagram Login."""

    empresa_id: UUID
    usuario_id: UUID
    codigo: str
    state: str


@dataclass(frozen=True, slots=True)
class CriarPostagemCmd:
    """Comando para criar rascunho ou postagem já agendada com mídias da conta."""

    empresa_id: UUID
    conta_ig_id: UUID
    tipo_midia: TipoMidia
    midia_ids: tuple[UUID, ...] = ()
    midias_chaves: tuple[str, ...] = ()
    legenda: str = ""
    agendado_para: datetime | None = None
    planejamento_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AgendarPostagemCmd:
    """Comando para agendar ou reagendar uma postagem para execução no Worker."""

    empresa_id: UUID
    conta_ig_id: UUID
    postagem_id: UUID
    agendado_para: datetime


@dataclass(frozen=True, slots=True)
class AnexarMidiasPostagemCmd:
    """Comando para anexar ou substituir mídias em rascunho/postagem existente."""

    empresa_id: UUID
    conta_ig_id: UUID
    postagem_id: UUID
    midia_ids: tuple[UUID, ...] = ()
    midias_chaves: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultadoPublicacaoDTO:
    """Resultado consolidado de uma tentativa de publicação oficial Meta."""

    postagem: Postagem
    publicada: bool
    reagendada: bool = False
    motivo: str = ""


@dataclass(frozen=True, slots=True)
class ResultadoLoteWorkerDTO:
    """Métricas de um ciclo de varredura de postagens agendadas no Worker."""

    pendentes_encontradas: int = 0
    publicadas: int = 0
    reagendadas: int = 0
    falhas: int = 0
    ignoradas_por_lock: int = 0
    recuperadas_travadas: int = 0


@dataclass(frozen=True, slots=True)
class ResultadoRenovacaoTokensDTO:
    """Métricas de um ciclo de renovação proativa de Long-Lived Tokens."""

    elegiveis: int = 0
    renovadas: int = 0
    falhas: int = 0
