"""Rotas HTTP para RAG (texto, arquivos PDF/TXT/MD, URLs públicas) e Brand Bible."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status

from app.api.dependencias.container_ia import ContainerIA
from app.api.dependencias.provedores_ia import obter_container_ia, obter_prompts_rag_uc
from app.api.dependencias.usuario_atual import obter_usuario_atual
from app.api.schemas.contas_rag import (
    CompilarBrandBibleRequest,
    ConfigIAResponse,
    FonteRagResponse,
    IndexarFonteRagRequest,
    IndexarUrlRagRequest,
)
from app.aplicacao.ia import (
    IndexarArquivoRagCmd,
    IndexarFonteRagCmd,
    IndexarUrlRagCmd,
    ServicoPromptsRagUseCase,
)
from app.dominio.entidades.ia_rag import ConfigIAConta, FonteRAG
from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG
from app.dominio.portas.seguranca import PayloadAccessToken

router = APIRouter(tags=["contas-rag"])


def to_config_response(cfg: ConfigIAConta) -> ConfigIAResponse:
    return ConfigIAResponse(
        id=cfg.id,
        empresa_id=cfg.empresa_id,
        conta_ig_id=cfg.conta_ig_id,
        persona_json=cfg.persona_json,
        templates_json=cfg.templates_json,
        brand_bible_json=cfg.brand_bible_json,
        aplicar_logo_padrao=cfg.aplicar_logo_padrao,
        modelo_texto_pref=cfg.modelo_texto_pref,
        modelo_img_pref=cfg.modelo_img_pref,
    )


def _to_rag_response(fonte: FonteRAG) -> FonteRagResponse:
    return FonteRagResponse(
        id=fonte.id,
        conta_ig_id=fonte.conta_ig_id,
        tipo=fonte.tipo,
        titulo=fonte.titulo,
        resumo_fatos=fonte.resumo_fatos,
        tem_embeddings=bool(fonte.embeddings_chunks),
        total_chunks=len(fonte.chunks),
        chunks=fonte.chunks,
        criado_em=fonte.criado_em,
    )


async def _ler_arquivo_limitado(arquivo: UploadFile, limite: int) -> bytes:
    blocos: list[bytes] = []
    total = 0
    while chunk := await arquivo.read(1024 * 1024):
        total += len(chunk)
        if total > limite:
            raise HTTPException(
                status_code=413,
                detail="Arquivo excede o limite permitido para RAG.",
            )
        blocos.append(chunk)
    return b"".join(blocos)


@router.get("/{conta_ig_id}/rag", response_model=list[FonteRagResponse])
async def listar_fontes_rag(
    conta_ig_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> list[FonteRagResponse]:
    return [_to_rag_response(f) for f in await uc.listar_fontes(ctx.empresa_id, conta_ig_id)]


@router.post(
    "/{conta_ig_id}/rag", response_model=FonteRagResponse, status_code=status.HTTP_201_CREATED
)
async def indexar_fonte_rag(
    conta_ig_id: UUID,
    payload: IndexarFonteRagRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> FonteRagResponse:
    fonte = await uc.indexar_fonte(
        IndexarFonteRagCmd(
            empresa_id=ctx.empresa_id,
            conta_ig_id=conta_ig_id,
            tipo=payload.tipo,
            titulo=payload.titulo,
            conteudo=payload.conteudo,
        )
    )
    return _to_rag_response(fonte)


@router.post(
    "/{conta_ig_id}/rag/arquivo",
    response_model=FonteRagResponse,
    status_code=status.HTTP_201_CREATED,
)
async def indexar_arquivo_rag(
    conta_ig_id: UUID,
    arquivo: UploadFile,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
    container: Annotated[ContainerIA, Depends(obter_container_ia)],
    tipo: Annotated[TipoFonteRAG, Form()] = TipoFonteRAG.DOCUMENTO,
    titulo: Annotated[str, Form()] = "",
) -> FonteRagResponse:
    conteudo = await _ler_arquivo_limitado(arquivo, container.config.rag_max_arquivo_bytes)
    fonte = await uc.indexar_arquivo(
        IndexarArquivoRagCmd(
            empresa_id=ctx.empresa_id,
            conta_ig_id=conta_ig_id,
            nome_arquivo=arquivo.filename or "documento.txt",
            conteudo_bytes=conteudo,
            tipo=tipo,
            titulo=titulo,
        )
    )
    return _to_rag_response(fonte)


@router.post(
    "/{conta_ig_id}/rag/url",
    response_model=FonteRagResponse,
    status_code=status.HTTP_201_CREATED,
)
async def indexar_url_rag(
    conta_ig_id: UUID,
    payload: IndexarUrlRagRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> FonteRagResponse:
    fonte = await uc.indexar_url(
        IndexarUrlRagCmd(
            empresa_id=ctx.empresa_id,
            conta_ig_id=conta_ig_id,
            url=payload.url,
            tipo=payload.tipo,
            titulo=payload.titulo,
        )
    )
    return _to_rag_response(fonte)


@router.delete("/{conta_ig_id}/rag/{fonte_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_fonte_rag(
    conta_ig_id: UUID,
    fonte_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> None:
    if not await uc.remover_fonte(ctx.empresa_id, conta_ig_id, fonte_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fonte RAG não encontrada."
        )


@router.post("/{conta_ig_id}/brand-bible/compilar", response_model=ConfigIAResponse)
async def compilar_brand_bible_conta(
    conta_ig_id: UUID,
    payload: CompilarBrandBibleRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> ConfigIAResponse:
    cfg = await uc.compilar_brand_bible(
        ctx.empresa_id, conta_ig_id, usar_ia=payload.usar_ia
    )
    return to_config_response(cfg)
