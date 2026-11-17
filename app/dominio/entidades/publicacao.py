"""Entidades de postagem e planejamento semanal com máquinas de estado."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import (
    StatusPlanejamento,
    StatusPostagem,
    TipoMidia,
)
from app.dominio.objetos_valor.maquina_estados import (
    validar_transicao_planejamento,
    validar_transicao_postagem,
)


@dataclass(slots=True)
class Postagem:
    """Unidade de conteúdo multi-formato preparada para publicação oficial."""

    empresa_id: UUID
    conta_ig_id: UUID
    tipo_midia: TipoMidia
    midias_chaves: list[str]
    legenda: str = ""
    status: StatusPostagem = StatusPostagem.RASCUNHO
    planejamento_id: UUID | None = None
    agendado_para: datetime | None = None
    idempotency_key: str = field(default_factory=lambda: str(uuid4()))
    meta_container_id: str | None = None
    meta_media_id: str | None = None
    erro_detalhe: str | None = None
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))
    tentativas_publicacao: int = 0
    atualizado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.validar_invariantes()

    def _tocar(self, agora: datetime | None = None) -> None:
        self.atualizado_em = agora or datetime.now(UTC)

    def validar_invariantes_midia(self) -> None:
        """Exige regras estritas da Meta Graph API para agendamento ou publicação."""
        qtd = len(self.midias_chaves)
        if self.tipo_midia == TipoMidia.CAROUSEL:
            if not 2 <= qtd <= 10:
                raise ErroValidacaoDominio("Carrossel exige entre 2 e 10 mídias.")
        elif qtd != 1:
            raise ErroValidacaoDominio(
                f"Formato {self.tipo_midia.value} exige exatamente 1 mídia."
            )
        if self.tipo_midia == TipoMidia.STORIES and self.legenda.strip():
            raise ErroValidacaoDominio("Stories não aceita legenda textual na Meta API.")

    def validar_invariantes(self) -> None:
        """Permite rascunho só-texto sem mídia; exige invariantes Meta nos demais casos."""
        if self.tentativas_publicacao < 0:
            raise ErroValidacaoDominio("Tentativas de publicação não pode ser negativo.")
        if self.tipo_midia == TipoMidia.STORIES and self.legenda.strip():
            raise ErroValidacaoDominio("Stories não aceita legenda textual na Meta API.")
        if self.status == StatusPostagem.RASCUNHO and not self.midias_chaves:
            return
        self.validar_invariantes_midia()

    def definir_midias(self, chaves: list[str], agora: datetime | None = None) -> None:
        """Anexa ou substitui mídias em postagens não finalizadas validando invariantes."""
        if self.status in {
            StatusPostagem.PUBLICANDO,
            StatusPostagem.PUBLICADO,
            StatusPostagem.CANCELADO,
        }:
            raise ErroValidacaoDominio(
                "Não é possível alterar mídias no status atual da postagem."
            )
        self.midias_chaves = list(chaves)
        self.validar_invariantes()
        self._tocar(agora)

    def agendar(self, para: datetime, agora: datetime | None = None) -> None:
        """Agenda a postagem para execução futura no Worker."""
        self.validar_invariantes_midia()
        validar_transicao_postagem(self.status, StatusPostagem.AGENDADO)
        self.agendado_para = para
        self.erro_detalhe = None
        self.status = StatusPostagem.AGENDADO
        self._tocar(agora)

    def iniciar_publicacao(self, agora: datetime | None = None) -> None:
        """Trava a postagem antes do envio à Meta."""
        self.validar_invariantes_midia()
        validar_transicao_postagem(self.status, StatusPostagem.PUBLICANDO)
        self.status = StatusPostagem.PUBLICANDO
        self._tocar(agora)

    def marcar_publicado(
        self,
        meta_media_id: str,
        meta_container_id: str | None = None,
        agora: datetime | None = None,
    ) -> None:
        """Finaliza postagem publicada com identificadores oficiais da Meta."""
        validar_transicao_postagem(self.status, StatusPostagem.PUBLICADO)
        if not meta_media_id.strip():
            raise ErroValidacaoDominio("meta_media_id é obrigatório ao concluir publicação.")
        self.meta_media_id = meta_media_id
        self.meta_container_id = meta_container_id or self.meta_container_id
        self.erro_detalhe = None
        self.status = StatusPostagem.PUBLICADO
        self._tocar(agora)

    def marcar_falha(self, detalhe: str, agora: datetime | None = None) -> None:
        """Registra falha detalhada para inspeção ou reagendamento."""
        validar_transicao_postagem(self.status, StatusPostagem.FALHA)
        self.erro_detalhe = detalhe.strip() or "Falha não especificada na publicação."
        self.status = StatusPostagem.FALHA
        self._tocar(agora)

    def reagendar_por_falha_transitoria(
        self, para: datetime, detalhe: str, agora: datetime | None = None
    ) -> None:
        """Devolve postagem de PUBLICANDO para AGENDADO incrementando tentativas."""
        self.validar_invariantes_midia()
        validar_transicao_postagem(self.status, StatusPostagem.AGENDADO)
        self.tentativas_publicacao += 1
        self.agendado_para = para
        self.erro_detalhe = detalhe.strip() or "Falha transitória na publicação."
        self.status = StatusPostagem.AGENDADO
        self._tocar(agora)

    def cancelar(self, agora: datetime | None = None) -> None:
        """Cancela postagem que ainda não entrou em publicação ou conclusão."""
        validar_transicao_postagem(self.status, StatusPostagem.CANCELADO)
        self.status = StatusPostagem.CANCELADO
        self._tocar(agora)


@dataclass(slots=True)
class PlanejamentoSemanal:
    """Grade semanal gerada em 2 etapas com estimativa de custo antes da execução."""

    empresa_id: UUID
    conta_ig_id: UUID
    semana_inicio: date
    itens_grade: list[dict[str, Any]] = field(default_factory=list)
    tendencias_cache: dict[str, Any] = field(default_factory=dict)
    custo_estimado_usd: Decimal = Decimal("0.0000")
    status: StatusPlanejamento = StatusPlanejamento.RASCUNHO
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.custo_estimado_usd < Decimal("0"):
            raise ErroValidacaoDominio("Custo estimado não pode ser negativo.")

    def enviar_para_aprovacao(self) -> None:
        validar_transicao_planejamento(self.status, StatusPlanejamento.AGUARDANDO_APROVACAO)
        self.status = StatusPlanejamento.AGUARDANDO_APROVACAO

    def aprovar(self) -> None:
        validar_transicao_planejamento(self.status, StatusPlanejamento.APROVADO)
        self.status = StatusPlanejamento.APROVADO

    def iniciar_execucao(self) -> None:
        validar_transicao_planejamento(self.status, StatusPlanejamento.EM_EXECUCAO)
        self.status = StatusPlanejamento.EM_EXECUCAO

    def concluir(self) -> None:
        validar_transicao_planejamento(self.status, StatusPlanejamento.CONCLUIDO)
        self.status = StatusPlanejamento.CONCLUIDO

    def marcar_falha(self) -> None:
        validar_transicao_planejamento(self.status, StatusPlanejamento.FALHA)
        self.status = StatusPlanejamento.FALHA

    def cancelar(self) -> None:
        validar_transicao_planejamento(self.status, StatusPlanejamento.CANCELADO)
        self.status = StatusPlanejamento.CANCELADO
