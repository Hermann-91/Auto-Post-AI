"""Provedores FastAPI (Depends) para rotas OAuth Meta e Postagens."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencias.container_ia import ContainerIA
from app.api.dependencias.container_meta import (
    ContainerMeta,
    criar_agendamento_uc,
    criar_oauth_meta_uc,
)
from app.api.dependencias.provedores_ia import obter_container_ia
from app.aplicacao.publicacao import ServicoAgendamentoUseCase, ServicoOAuthMetaUseCase


def obter_container_meta(request: Request) -> ContainerMeta:
    """Recupera o ContainerMeta anexado à instância FastAPI."""
    return cast(ContainerMeta, request.app.state.meta_container)


def obter_oauth_meta_uc(
    ia: Annotated[ContainerIA, Depends(obter_container_ia)],
    meta: Annotated[ContainerMeta, Depends(obter_container_meta)],
) -> ServicoOAuthMetaUseCase:
    return criar_oauth_meta_uc(ia, meta)


def obter_agendamento_uc(
    ia: Annotated[ContainerIA, Depends(obter_container_ia)],
    meta: Annotated[ContainerMeta, Depends(obter_container_meta)],
) -> ServicoAgendamentoUseCase:
    return criar_agendamento_uc(ia, meta)
