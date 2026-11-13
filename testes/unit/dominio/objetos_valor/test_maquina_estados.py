"""Testes unitários das máquinas de estado de postagem e planejamento."""

from __future__ import annotations

import pytest

from app.dominio.excecoes import ErroTransicaoEstado
from app.dominio.objetos_valor.enums_conteudo import StatusPlanejamento, StatusPostagem
from app.dominio.objetos_valor.maquina_estados import (
    validar_transicao_planejamento,
    validar_transicao_postagem,
)


def test_transicoes_validas_e_invalidas_postagem() -> None:
    validar_transicao_postagem(StatusPostagem.RASCUNHO, StatusPostagem.AGENDADO)
    validar_transicao_postagem(StatusPostagem.AGENDADO, StatusPostagem.PUBLICANDO)
    validar_transicao_postagem(StatusPostagem.PUBLICANDO, StatusPostagem.PUBLICADO)

    with pytest.raises(ErroTransicaoEstado):
        validar_transicao_postagem(StatusPostagem.PUBLICADO, StatusPostagem.AGENDADO)
    with pytest.raises(ErroTransicaoEstado):
        validar_transicao_postagem(StatusPostagem.RASCUNHO, StatusPostagem.PUBLICADO)


def test_transicoes_validas_e_invalidas_planejamento() -> None:
    validar_transicao_planejamento(
        StatusPlanejamento.RASCUNHO,
        StatusPlanejamento.AGUARDANDO_APROVACAO,
    )
    validar_transicao_planejamento(
        StatusPlanejamento.AGUARDANDO_APROVACAO,
        StatusPlanejamento.APROVADO,
    )

    with pytest.raises(ErroTransicaoEstado):
        validar_transicao_planejamento(
            StatusPlanejamento.RASCUNHO,
            StatusPlanejamento.EM_EXECUCAO,
        )
