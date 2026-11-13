"""Rotas HTTP para criação, agendamento, cancelamento e publicação de postagens."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencias.provedores_meta import obter_agendamento_uc
from app.api.dependencias.usuario_atual import obter_usuario_atual
from app.api.schemas.postagens_meta import (
    AgendarPostagemRequest,
    CriarPostagemRequest,
    PostagemDetalheResponse,
    ResultadoPublicacaoResponse,
)
from app.aplicacao.publicacao import (
    AgendarPostagemCmd,
    CriarPostagemCmd,
    ServicoAgendamentoUseCase,
)
from app.dominio.entidades.publicacao import Postagem
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem
from app.dominio.portas.seguranca import PayloadAccessToken

router = APIRouter(prefix="/posts", tags=["postagens"])


def _to_post_detalhe(post: Postagem) -> PostagemDetalheResponse:
    return PostagemDetalheResponse(
        id=post.id,
        conta_ig_id=post.conta_ig_id,
        tipo_midia=post.tipo_midia,
        midias_chaves=post.midias_chaves,
        legenda=post.legenda,
        status=post.status,
        planejamento_id=post.planejamento_id,
        agendado_para=post.agendado_para,
        meta_container_id=post.meta_container_id,
        meta_media_id=post.meta_media_id,
        erro_detalhe=post.erro_detalhe,
        criado_em=post.criado_em,
    )


@router.post("", response_model=PostagemDetalheResponse, status_code=status.HTTP_201_CREATED)
async def criar_postagem(
    payload: CriarPostagemRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoAgendamentoUseCase, Depends(obter_agendamento_uc)],
) -> PostagemDetalheResponse:
    """Cria rascunho ou postagem já agendada com mídias da conta."""
    post = await uc.criar_postagem(
        CriarPostagemCmd(
            empresa_id=ctx.empresa_id,
            conta_ig_id=payload.conta_ig_id,
            tipo_midia=payload.tipo_midia,
            midia_ids=tuple(payload.midia_ids),
            midias_chaves=tuple(payload.midias_chaves),
            legenda=payload.legenda,
            agendado_para=payload.agendado_para,
            planejamento_id=payload.planejamento_id,
        )
    )
    return _to_post_detalhe(post)


@router.get("/{conta_ig_id}", response_model=list[PostagemDetalheResponse])
async def listar_postagens_conta(
    conta_ig_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoAgendamentoUseCase, Depends(obter_agendamento_uc)],
    status_filtro: Annotated[StatusPostagem | None, Query(alias="status")] = None,
) -> list[PostagemDetalheResponse]:
    posts = await uc.listar_postagens(ctx.empresa_id, conta_ig_id, status=status_filtro)
    return [_to_post_detalhe(p) for p in posts]


@router.get("/{conta_ig_id}/{postagem_id}", response_model=PostagemDetalheResponse)
async def obter_postagem(
    conta_ig_id: UUID,
    postagem_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoAgendamentoUseCase, Depends(obter_agendamento_uc)],
) -> PostagemDetalheResponse:
    post = await uc.obter_postagem(ctx.empresa_id, conta_ig_id, postagem_id)
    return _to_post_detalhe(post)


@router.post("/{conta_ig_id}/{postagem_id}/agendar", response_model=PostagemDetalheResponse)
async def agendar_postagem(
    conta_ig_id: UUID,
    postagem_id: UUID,
    payload: AgendarPostagemRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoAgendamentoUseCase, Depends(obter_agendamento_uc)],
) -> PostagemDetalheResponse:
    post = await uc.agendar_postagem(
        AgendarPostagemCmd(
            empresa_id=ctx.empresa_id,
            conta_ig_id=conta_ig_id,
            postagem_id=postagem_id,
            agendado_para=payload.agendado_para,
        )
    )
    return _to_post_detalhe(post)


@router.post(
    "/{conta_ig_id}/{postagem_id}/publicar-agora",
    response_model=ResultadoPublicacaoResponse,
)
async def publicar_postagem_agora(
    conta_ig_id: UUID,
    postagem_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoAgendamentoUseCase, Depends(obter_agendamento_uc)],
) -> ResultadoPublicacaoResponse:
    res = await uc.publicar_postagem(
        ctx.empresa_id, conta_ig_id, postagem_id, permitir_imediata=True
    )
    return ResultadoPublicacaoResponse(
        postagem=_to_post_detalhe(res.postagem),
        publicada=res.publicada,
        reagendada=res.reagendada,
        motivo=res.motivo,
    )


@router.post("/{conta_ig_id}/{postagem_id}/cancelar", response_model=PostagemDetalheResponse)
async def cancelar_postagem(
    conta_ig_id: UUID,
    postagem_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoAgendamentoUseCase, Depends(obter_agendamento_uc)],
) -> PostagemDetalheResponse:
    post = await uc.cancelar_postagem(ctx.empresa_id, conta_ig_id, postagem_id)
    return _to_post_detalhe(post)
