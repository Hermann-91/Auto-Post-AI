"""Rotas HTTP para geração individual de conteúdo e curadoria visual IA."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencias.provedores_ia import obter_criar_conteudo_uc, obter_curadoria_uc
from app.api.dependencias.usuario_atual import obter_usuario_atual
from app.api.schemas.criacao_ia import (
    CriarConteudoRequest,
    CriarConteudoResponse,
    CuradoriaVisualResponse,
    MidiaResumoResponse,
    PostagemResumoResponse,
)
from app.aplicacao.ia import (
    CriarConteudoCmd,
    CriarConteudoUseCase,
    ServicoCuradoriaVisualUseCase,
)
from app.dominio.entidades.publicacao import Postagem
from app.dominio.portas.seguranca import PayloadAccessToken

router = APIRouter(prefix="/ia", tags=["criacao-ia"])


def to_postagem_resumo(post: Postagem) -> PostagemResumoResponse:
    """Converte entidade Postagem em resumo seguro para a API."""
    return PostagemResumoResponse(
        id=post.id,
        conta_ig_id=post.conta_ig_id,
        tipo_midia=post.tipo_midia,
        midias_chaves=post.midias_chaves,
        legenda=post.legenda,
        status=post.status,
        planejamento_id=post.planejamento_id,
    )


@router.post("/criar", response_model=CriarConteudoResponse)
async def criar_conteudo(
    payload: CriarConteudoRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[CriarConteudoUseCase, Depends(obter_criar_conteudo_uc)],
) -> CriarConteudoResponse:
    """Gera texto/hashtags via DeepSeek, imagem opcional via Nano Banana e rascunho."""
    res = await uc.executar(
        CriarConteudoCmd(
            empresa_id=ctx.empresa_id,
            conta_ig_id=payload.conta_ig_id,
            tipo_midia=payload.tipo_midia,
            tema=payload.tema,
            objetivo=payload.objetivo,
            tom_extra=payload.tom_extra,
            gerar_imagem_ia=payload.gerar_imagem_ia,
            editar_midia_id=payload.editar_midia_id,
            midia_base_ids=tuple(payload.midia_base_ids),
            prompt_visual_extra=payload.prompt_visual_extra,
            presets_melhoria=tuple(payload.presets_melhoria),
            proporcao=payload.proporcao,
            aplicar_logo=payload.aplicar_logo,
            salvar_rascunho=payload.salvar_rascunho,
            modelo_texto=payload.modelo_texto,
            modelo_imagem=payload.modelo_imagem,
        )
    )
    return CriarConteudoResponse(
        legenda=res.legenda,
        hashtags=res.hashtags,
        prompt_visual=res.prompt_visual,
        roteiro_slides=res.roteiro_slides,
        midias_geradas=[
            MidiaResumoResponse(
                id=m.id,
                pasta=m.pasta,
                chave_storage=m.chave_storage,
                tipo_arquivo=m.tipo_arquivo,
                tamanho_bytes=m.tamanho_bytes,
                curtida_favorita=m.curtida_favorita,
                resumo_visual=m.resumo_visual,
            )
            for m in res.midias_geradas
        ],
        postagem=to_postagem_resumo(res.postagem) if res.postagem else None,
        custo_total_usd=res.custo_total_usd,
        modelos_usados=res.modelos_usados,
        modo_economico_ativado=res.modo_economico_ativado,
    )


@router.post("/curadoria/{conta_ig_id}/{midia_id}", response_model=CuradoriaVisualResponse)
async def curar_midia(
    conta_ig_id: UUID,
    midia_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoCuradoriaVisualUseCase, Depends(obter_curadoria_uc)],
) -> CuradoriaVisualResponse:
    """Analisa imagem compactada (<= 1024px) para alimentar âncoras visuais."""
    res = await uc.curar_midia(ctx.empresa_id, conta_ig_id, midia_id)
    return CuradoriaVisualResponse(
        midia_id=res.midia.id,
        resumo_visual=res.resumo_visual,
        custo_usd=res.custo_usd,
        modelo_usado=res.modelo_usado,
    )
