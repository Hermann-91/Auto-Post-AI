"""Rotas HTTP para o fluxo em 2 etapas do Planejamento Semanal Automatizado."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencias.provedores_ia import obter_planejamento_uc
from app.api.dependencias.usuario_atual import obter_usuario_atual
from app.api.rotas.criacao import to_postagem_resumo
from app.api.schemas.criacao_ia import (
    ExecucaoPlanejamentoResponse,
    PlanejamentoResponse,
    ProporPlanejamentoRequest,
)
from app.aplicacao.ia import PlanejamentoSemanalUseCase, ProporPlanejamentoCmd
from app.dominio.entidades.publicacao import PlanejamentoSemanal
from app.dominio.portas.seguranca import PayloadAccessToken

router = APIRouter(prefix="/planejamento", tags=["planejamento-semanal"])


def _to_plano_response(plano: PlanejamentoSemanal) -> PlanejamentoResponse:
    return PlanejamentoResponse(
        id=plano.id,
        conta_ig_id=plano.conta_ig_id,
        semana_inicio=plano.semana_inicio,
        status=plano.status,
        custo_estimado_usd=plano.custo_estimado_usd,
        itens_grade=plano.itens_grade,
        tendencias_cache=plano.tendencias_cache,
        criado_em=plano.criado_em,
    )


@router.post("/propor", response_model=PlanejamentoResponse, status_code=status.HTTP_201_CREATED)
async def propor_planejamento(
    payload: ProporPlanejamentoRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[PlanejamentoSemanalUseCase, Depends(obter_planejamento_uc)],
) -> PlanejamentoResponse:
    """Etapa 1: gera grade semanal em JSON com tendências em cache e estimativa USD."""
    plano = await uc.propor_semana(
        ProporPlanejamentoCmd(
            empresa_id=ctx.empresa_id,
            conta_ig_id=payload.conta_ig_id,
            semana_inicio=payload.semana_inicio,
            nicho=payload.nicho,
            regiao=payload.regiao,
            objetivo_semana=payload.objetivo_semana,
            quantidade_posts=payload.quantidade_posts,
            incluir_imagens_ia=payload.incluir_imagens_ia,
            ttl_tendencias_horas=payload.ttl_tendencias_horas,
        )
    )
    return _to_plano_response(plano)


@router.get("/{conta_ig_id}", response_model=list[PlanejamentoResponse])
async def listar_planejamentos(
    conta_ig_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[PlanejamentoSemanalUseCase, Depends(obter_planejamento_uc)],
) -> list[PlanejamentoResponse]:
    planos = await uc.listar_planos(ctx.empresa_id, conta_ig_id)
    return [_to_plano_response(p) for p in planos]


@router.get("/{conta_ig_id}/{plano_id}", response_model=PlanejamentoResponse)
async def obter_planejamento(
    conta_ig_id: UUID,
    plano_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[PlanejamentoSemanalUseCase, Depends(obter_planejamento_uc)],
) -> PlanejamentoResponse:
    plano = await uc.obter_plano(ctx.empresa_id, conta_ig_id, plano_id)
    return _to_plano_response(plano)


@router.post("/{conta_ig_id}/{plano_id}/aprovar", response_model=PlanejamentoResponse)
async def aprovar_planejamento(
    conta_ig_id: UUID,
    plano_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[PlanejamentoSemanalUseCase, Depends(obter_planejamento_uc)],
) -> PlanejamentoResponse:
    """Etapa 2a: verifica disponibilidade de orçamento e aprova grade para execução."""
    plano = await uc.aprovar_plano(ctx.empresa_id, conta_ig_id, plano_id)
    return _to_plano_response(plano)


@router.post("/{conta_ig_id}/{plano_id}/executar", response_model=ExecucaoPlanejamentoResponse)
async def executar_planejamento(
    conta_ig_id: UUID,
    plano_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[PlanejamentoSemanalUseCase, Depends(obter_planejamento_uc)],
) -> ExecucaoPlanejamentoResponse:
    """Etapa 2b: executa os itens aprovados gerando mídias em IA-Cria e rascunhos."""
    res = await uc.executar_plano(ctx.empresa_id, conta_ig_id, plano_id)
    return ExecucaoPlanejamentoResponse(
        plano=_to_plano_response(res.plano),
        postagens_criadas=[to_postagem_resumo(p) for p in res.postagens_criadas],
        falhas_itens=res.falhas_itens,
        custo_real_usd=res.custo_real_usd,
    )
