"""Rotas HTTP para biblioteca de mídia, cota, upload, curtidas e limpeza."""

from __future__ import annotations

import mimetypes
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, UploadFile, status

from app.api.dependencias.container_servicos import (
    obter_exclusao_uc,
    obter_limpeza_uc,
    obter_upload_cota_uc,
)
from app.api.dependencias.provedores_ia import obter_prompts_rag_uc
from app.api.dependencias.usuario_atual import obter_usuario_atual
from app.api.schemas.biblioteca import (
    AlternarCurtidaRequest,
    MidiaBibliotecaResponse,
    ResultadoExclusaoMidiaResponse,
    ResultadoLimpezaResponse,
    ResumoCotaResponse,
)
from app.aplicacao.biblioteca import (
    MidiaComUrlDTO,
    ServicoExclusaoMidiaPostUseCase,
    ServicoLimpezaPosPostagemUseCase,
    ServicoUploadCotaUseCase,
    UploadMidiaCmd,
)
from app.aplicacao.biblioteca.servico_upload_cota import TAMANHO_MAX_ARQUIVO_BYTES
from app.aplicacao.ia import ServicoPromptsRagUseCase
from app.dominio.objetos_valor.enums_conteudo import PastaMidia
from app.dominio.portas.seguranca import PayloadAccessToken

router = APIRouter(prefix="/biblioteca", tags=["biblioteca-midia"])


def _to_midia_response(dto: MidiaComUrlDTO) -> MidiaBibliotecaResponse:
    m = dto.midia
    return MidiaBibliotecaResponse(
        id=m.id,
        conta_ig_id=m.conta_ig_id,
        pasta=m.pasta,
        chave_storage=m.chave_storage,
        url_publica=dto.url_publica,
        tipo_arquivo=m.tipo_arquivo,
        tamanho_bytes=m.tamanho_bytes,
        curtida_favorita=m.curtida_favorita,
        resumo_visual=m.resumo_visual,
        criado_em=m.criado_em,
    )


async def _ler_upload_limitado(arquivo: UploadFile, limite: int) -> bytes:
    blocos: list[bytes] = []
    total = 0
    while chunk := await arquivo.read(1024 * 1024):
        total += len(chunk)
        if total > limite:
            raise HTTPException(
                status_code=413,
                detail="Arquivo excede o limite individual permitido.",
            )
        blocos.append(chunk)
    return b"".join(blocos)


def _resolver_content_type(arquivo: UploadFile) -> str:
    tipo = (arquivo.content_type or "").strip().lower()
    if not tipo or tipo == "application/octet-stream":
        adivinhado, _ = mimetypes.guess_type(arquivo.filename or "")
        return (adivinhado or "application/octet-stream").lower()
    return tipo


@router.get("/{conta_ig_id}", response_model=list[MidiaBibliotecaResponse])
async def listar_midias_conta(
    conta_ig_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoUploadCotaUseCase, Depends(obter_upload_cota_uc)],
    pasta: Annotated[PastaMidia | None, Query()] = None,
) -> list[MidiaBibliotecaResponse]:
    """Lista mídias da conta autenticada com filtro opcional de pasta."""
    itens = await uc.listar_midias(ctx.empresa_id, conta_ig_id, pasta=pasta)
    return [_to_midia_response(item) for item in itens]


@router.get("/{conta_ig_id}/cota", response_model=ResumoCotaResponse)
async def consultar_cota_conta(
    conta_ig_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoUploadCotaUseCase, Depends(obter_upload_cota_uc)],
) -> ResumoCotaResponse:
    """Retorna consumo atual (X/250 mídias e bytes) da conta Instagram."""
    resumo = await uc.obter_resumo_cota(ctx.empresa_id, conta_ig_id)
    return ResumoCotaResponse(
        itens_usados=resumo.itens_usados,
        max_itens=resumo.max_itens,
        percentual_itens=resumo.percentual_itens,
        bytes_usados=resumo.bytes_usados,
        max_bytes=resumo.max_bytes,
        percentual_bytes=resumo.percentual_bytes,
    )


@router.post(
    "/{conta_ig_id}/upload",
    response_model=MidiaBibliotecaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enviar_midia(
    conta_ig_id: UUID,
    arquivo: UploadFile,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoUploadCotaUseCase, Depends(obter_upload_cota_uc)],
    pasta: Annotated[PastaMidia, Form()] = PastaMidia.ORIGINAIS,
    resumo_visual: Annotated[str, Form()] = "",
) -> MidiaBibliotecaResponse:
    """Recebe arquivo direto do dispositivo, compacta imagens e valida cota."""
    conteudo = await _ler_upload_limitado(arquivo, TAMANHO_MAX_ARQUIVO_BYTES)
    dto = await uc.registrar_upload(
        UploadMidiaCmd(
            empresa_id=ctx.empresa_id,
            conta_ig_id=conta_ig_id,
            pasta=pasta,
            nome_arquivo=arquivo.filename or "midia.jpg",
            content_type=_resolver_content_type(arquivo),
            conteudo=conteudo,
            resumo_visual=resumo_visual.strip()[:400],
        )
    )
    return _to_midia_response(dto)


@router.patch("/{conta_ig_id}/{midia_id}/curtida", response_model=MidiaBibliotecaResponse)
async def alternar_curtida_midia(
    conta_ig_id: UUID,
    midia_id: UUID,
    payload: AlternarCurtidaRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoUploadCotaUseCase, Depends(obter_upload_cota_uc)],
) -> MidiaBibliotecaResponse:
    """Fixa ou desfixa mídia como favorita protegida contra limpeza."""
    salva = await uc.alternar_curtida(ctx.empresa_id, conta_ig_id, midia_id, payload.favorita)
    itens = await uc.listar_midias(ctx.empresa_id, conta_ig_id, pasta=salva.pasta)
    for item in itens:
        if item.midia.id == salva.id:
            return _to_midia_response(item)
    return _to_midia_response(MidiaComUrlDTO(midia=salva, url_publica=""))


@router.post("/{conta_ig_id}/limpar-pos-postagem", response_model=ResultadoLimpezaResponse)
async def limpar_midias_pos_postagem(
    conta_ig_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    prompts_uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
    limpeza_uc: Annotated[ServicoLimpezaPosPostagemUseCase, Depends(obter_limpeza_uc)],
) -> ResultadoLimpezaResponse:
    """Remove mídias já publicadas preservando curtidas e filas ativas."""
    await prompts_uc.exigir_conta(ctx.empresa_id, conta_ig_id)
    res = await limpeza_uc.executar(ctx.empresa_id, conta_ig_id)
    return ResultadoLimpezaResponse(
        removidas_qtd=res.removidas_qtd,
        bytes_liberados=res.bytes_liberados,
        chaves_removidas=res.chaves_removidas,
        falhas=res.falhas,
    )


@router.get("/{conta_ig_id}/midias/{midia_id}/conteudo")
async def baixar_preview_autenticado(
    conta_ig_id: UUID,
    midia_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoUploadCotaUseCase, Depends(obter_upload_cota_uc)],
) -> Response:
    """Serve bytes da mídia apenas ao tenant autenticado para preview no painel."""
    midia, dados = await uc.obter_conteudo_midia(ctx.empresa_id, conta_ig_id, midia_id)
    return Response(
        content=dados,
        media_type=midia.tipo_arquivo,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete("/{conta_ig_id}/{midia_id}", response_model=ResultadoExclusaoMidiaResponse)
async def excluir_midia_biblioteca(
    conta_ig_id: UUID,
    midia_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoExclusaoMidiaPostUseCase, Depends(obter_exclusao_uc)],
) -> ResultadoExclusaoMidiaResponse:
    """Exclui mídia do storage e do banco caso não esteja em card ativo da Agenda."""
    res = await uc.excluir_midia_biblioteca(ctx.empresa_id, conta_ig_id, midia_id)
    return ResultadoExclusaoMidiaResponse(
        midia_id=res.midia_id, chave_storage=res.chave_storage, bytes_liberados=res.bytes_liberados
    )
