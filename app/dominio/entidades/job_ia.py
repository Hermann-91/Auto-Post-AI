"""Entidade de domínio e estados para rastreamento de jobs assíncronos de IA."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.dominio.excecoes import ErroValidacaoDominio


class TipoJobIA(StrEnum):
    """Tipos de operações assíncronas suportadas no Estúdio e na Agenda."""

    CRIAR_CONTEUDO = "CRIAR_CONTEUDO"
    PROPOR_PLANO = "PROPOR_PLANO"
    EXECUTAR_PLANO = "EXECUTAR_PLANO"
    RECRIAR_POSTAGEM = "RECRIAR_POSTAGEM"


class StatusJobIA(StrEnum):
    """Ciclo de vida de execução de um job de IA."""

    PENDENTE = "PENDENTE"
    EXECUTANDO = "EXECUTANDO"
    CONCLUIDO = "CONCLUIDO"
    FALHA = "FALHA"


@dataclass(slots=True)
class JobIA:
    """Job assíncrono isolado por (empresa_id, conta_ig_id) com progresso X/Y."""

    empresa_id: UUID
    conta_ig_id: UUID
    tipo_job: TipoJobIA
    status: StatusJobIA = StatusJobIA.PENDENTE
    etapa_atual: str = "Na fila"
    progresso_atual: int = 0
    progresso_total: int = 1
    chave_idempotencia: str = ""
    resultado_json: dict[str, Any] | None = None
    erro_detalhe: str | None = None
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))
    atualizado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.chave_idempotencia = self.chave_idempotencia.strip()
        if self.progresso_total < 1:
            raise ErroValidacaoDominio("Progresso total do job deve ser maior ou igual a 1.")
        if self.progresso_atual < 0 or self.progresso_atual > self.progresso_total:
            raise ErroValidacaoDominio("Progresso atual do job fora dos limites válidos.")

    @property
    def finalizado(self) -> bool:
        return self.status in {StatusJobIA.CONCLUIDO, StatusJobIA.FALHA}

    @property
    def percentual(self) -> int:
        return min(100, max(0, int((self.progresso_atual / self.progresso_total) * 100)))

    def iniciar(self, etapa: str, progresso_total: int | None = None) -> None:
        if progresso_total is not None:
            if progresso_total < 1:
                raise ErroValidacaoDominio("Progresso total do job deve ser >= 1.")
            self.progresso_total = progresso_total
            self.progresso_atual = min(self.progresso_atual, self.progresso_total)
        self.status = StatusJobIA.EXECUTANDO
        self.etapa_atual = etapa.strip() or "Executando"
        self.atualizado_em = datetime.now(UTC)

    def avancar(self, progresso_atual: int, etapa: str) -> None:
        if self.finalizado:
            return
        self.progresso_atual = max(0, min(progresso_atual, self.progresso_total))
        self.etapa_atual = etapa.strip() or self.etapa_atual
        self.atualizado_em = datetime.now(UTC)

    def concluir(self, resultado_json: dict[str, Any], etapa: str = "Concluído") -> None:
        self.status = StatusJobIA.CONCLUIDO
        self.progresso_atual = self.progresso_total
        self.etapa_atual = etapa.strip() or "Concluído"
        self.resultado_json = resultado_json
        self.erro_detalhe = None
        self.atualizado_em = datetime.now(UTC)

    def falhar(self, erro_detalhe: str) -> None:
        self.status = StatusJobIA.FALHA
        self.etapa_atual = "Falha na execução"
        self.erro_detalhe = erro_detalhe.strip() or "Falha desconhecida no processamento."
        self.atualizado_em = datetime.now(UTC)
