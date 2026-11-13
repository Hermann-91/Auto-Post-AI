"""Máquinas de estado declarativas para postagens e planejamentos semanais."""

from __future__ import annotations

from app.dominio.excecoes import ErroTransicaoEstado
from app.dominio.objetos_valor.enums_conteudo import StatusPlanejamento, StatusPostagem

TRANSICOES_POSTAGEM: dict[StatusPostagem, frozenset[StatusPostagem]] = {
    StatusPostagem.RASCUNHO: frozenset({
        StatusPostagem.AGENDADO,
        StatusPostagem.CANCELADO,
    }),
    StatusPostagem.AGENDADO: frozenset({
        StatusPostagem.PUBLICANDO,
        StatusPostagem.RASCUNHO,
        StatusPostagem.CANCELADO,
    }),
    StatusPostagem.PUBLICANDO: frozenset({
        StatusPostagem.PUBLICADO,
        StatusPostagem.FALHA,
    }),
    StatusPostagem.FALHA: frozenset({
        StatusPostagem.AGENDADO,
        StatusPostagem.RASCUNHO,
        StatusPostagem.CANCELADO,
    }),
    StatusPostagem.PUBLICADO: frozenset(),
    StatusPostagem.CANCELADO: frozenset(),
}

TRANSICOES_PLANEJAMENTO: dict[StatusPlanejamento, frozenset[StatusPlanejamento]] = {
    StatusPlanejamento.RASCUNHO: frozenset({
        StatusPlanejamento.AGUARDANDO_APROVACAO,
        StatusPlanejamento.CANCELADO,
    }),
    StatusPlanejamento.AGUARDANDO_APROVACAO: frozenset({
        StatusPlanejamento.APROVADO,
        StatusPlanejamento.RASCUNHO,
        StatusPlanejamento.CANCELADO,
    }),
    StatusPlanejamento.APROVADO: frozenset({
        StatusPlanejamento.EM_EXECUCAO,
        StatusPlanejamento.CANCELADO,
    }),
    StatusPlanejamento.EM_EXECUCAO: frozenset({
        StatusPlanejamento.CONCLUIDO,
        StatusPlanejamento.FALHA,
    }),
    StatusPlanejamento.FALHA: frozenset({
        StatusPlanejamento.APROVADO,
        StatusPlanejamento.CANCELADO,
    }),
    StatusPlanejamento.CONCLUIDO: frozenset(),
    StatusPlanejamento.CANCELADO: frozenset(),
}


def validar_transicao_postagem(atual: StatusPostagem, destino: StatusPostagem) -> None:
    """Garante que a postagem siga apenas transições permitidas."""
    permitidos = TRANSICOES_POSTAGEM.get(atual, frozenset())
    if destino not in permitidos:
        raise ErroTransicaoEstado(
            f"Transição inválida de postagem: {atual.value} -> {destino.value}."
        )


def validar_transicao_planejamento(
    atual: StatusPlanejamento,
    destino: StatusPlanejamento,
) -> None:
    """Garante que o planejamento semanal siga o fluxo aprovado em 2 etapas."""
    permitidos = TRANSICOES_PLANEJAMENTO.get(atual, frozenset())
    if destino not in permitidos:
        raise ErroTransicaoEstado(
            f"Transição inválida de planejamento: {atual.value} -> {destino.value}."
        )
