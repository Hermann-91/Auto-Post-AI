"""Rotas HTTP para contas Instagram, ConfigIA/Persona, RAG e Orçamento USD."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencias.container_ia import ContainerIA
from app.api.dependencias.container_meta import ContainerMeta
from app.api.dependencias.provedores_ia import (
    obter_container_ia,
    obter_orcamento_uc,
    obter_prompts_rag_uc,
)
from app.api.dependencias.provedores_meta import obter_container_meta
from app.api.dependencias.usuario_atual import obter_usuario_atual
from app.api.schemas.criacao_ia import (
    AtualizarConfigIARequest,
    ConfigIAResponse,
    ContaInstagramResumoResponse,
    FonteRagResponse,
    IndexarFonteRagRequest,
    ResumoOrcamentoResponse,
    SalvarContaInstagramRequest,
)
from app.aplicacao.ia import (
    AtualizarConfigIACmd,
    IndexarFonteRagCmd,
    ServicoOrcamentoUseCase,
    ServicoPromptsRagUseCase,
)
from app.dominio.entidades.ia_rag import ConfigIAConta, FonteRAG
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.portas.seguranca import PayloadAccessToken

router = APIRouter(prefix="/contas", tags=["contas-ia"])


def _to_conta_resumo(c: ContaInstagram) -> ContaInstagramResumoResponse:
    return ContaInstagramResumoResponse(
        id=c.id, ig_user_id=c.ig_user_id, username=c.username, provedor=c.provedor, ativa=c.ativa
    )


def _to_config_response(cfg: ConfigIAConta) -> ConfigIAResponse:
    return ConfigIAResponse(
        id=cfg.id, empresa_id=cfg.empresa_id, conta_ig_id=cfg.conta_ig_id,
        persona_json=cfg.persona_json, templates_json=cfg.templates_json,
        aplicar_logo_padrao=cfg.aplicar_logo_padrao,
        modelo_texto_pref=cfg.modelo_texto_pref, modelo_img_pref=cfg.modelo_img_pref,
    )


def _to_rag_response(fonte: FonteRAG) -> FonteRagResponse:
    return FonteRagResponse(
        id=fonte.id, conta_ig_id=fonte.conta_ig_id, tipo=fonte.tipo, titulo=fonte.titulo,
        total_chunks=len(fonte.chunks), chunks=fonte.chunks, criado_em=fonte.criado_em,
    )


@router.get("", response_model=list[ContaInstagramResumoResponse])
async def listar_contas_empresa(
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    container: Annotated[ContainerIA, Depends(obter_container_ia)],
) -> list[ContaInstagramResumoResponse]:
    contas = await container.conta_repo.listar_por_empresa(ctx.empresa_id)
    return [_to_conta_resumo(c) for c in contas]


@router.post("", response_model=ContaInstagramResumoResponse, status_code=status.HTTP_201_CREATED)
async def salvar_conta_instagram(
    payload: SalvarContaInstagramRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    container: Annotated[ContainerIA, Depends(obter_container_ia)],
    meta: Annotated[ContainerMeta, Depends(obter_container_meta)],
) -> ContaInstagramResumoResponse:
    username = payload.username.strip().lstrip("@")
    if not username:
        raise ErroValidacaoDominio("Informe um @username válido.")
    ig_user_id = payload.ig_user_id.strip() or (
        f"sandbox_{username.lower()}" if payload.modo_sandbox else ""
    )
    if not ig_user_id:
        raise ErroValidacaoDominio("Informe o IG User ID da Meta ou use o Modo Teste/Sandbox.")
    conta = (
        await container.conta_repo.buscar_por_id(ctx.empresa_id, payload.conta_id)
        if payload.conta_id
        else None
    )
    if payload.conta_id and conta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta Instagram não encontrada."
        )
    conta = conta or await container.conta_repo.buscar_por_ig_user_id(ctx.empresa_id, ig_user_id)
    expira_em = datetime.now(UTC) + timedelta(days=payload.validade_dias)
    token_plano = payload.access_token.strip() or (
        f"sandbox_token_{username.lower()}" if payload.modo_sandbox and not conta else ""
    )
    if conta is not None:
        conta.username, conta.ig_user_id, conta.ativa = username, ig_user_id, True
        if token_plano:
            conta.atualizar_token(meta.cripto.criptografar(token_plano), expira_em)
    else:
        if not token_plano:
            raise ErroValidacaoDominio("Informe o Access Token da Meta ou use o Modo Sandbox.")
        conta = ContaInstagram(
            empresa_id=ctx.empresa_id, ig_user_id=ig_user_id, username=username,
            access_token_enc=meta.cripto.criptografar(token_plano), token_expira_em=expira_em,
        )
    return _to_conta_resumo(await container.conta_repo.salvar(conta))


@router.get("/{conta_ig_id}/ia-config", response_model=ConfigIAResponse)
async def obter_config_ia(
    conta_ig_id: UUID, ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> ConfigIAResponse:
    return _to_config_response(await uc.obter_config(ctx.empresa_id, conta_ig_id))


@router.put("/{conta_ig_id}/ia-config", response_model=ConfigIAResponse)
async def atualizar_config_ia(
    conta_ig_id: UUID, payload: AtualizarConfigIARequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> ConfigIAResponse:
    salva = await uc.atualizar_config(
        AtualizarConfigIACmd(
            empresa_id=ctx.empresa_id, conta_ig_id=conta_ig_id,
            persona_json=payload.persona_json, templates_json=payload.templates_json,
            aplicar_logo_padrao=payload.aplicar_logo_padrao,
            modelo_texto_pref=payload.modelo_texto_pref, modelo_img_pref=payload.modelo_img_pref,
        )
    )
    return _to_config_response(salva)


@router.get("/{conta_ig_id}/rag", response_model=list[FonteRagResponse])
async def listar_fontes_rag(
    conta_ig_id: UUID, ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> list[FonteRagResponse]:
    return [_to_rag_response(f) for f in await uc.listar_fontes(ctx.empresa_id, conta_ig_id)]


@router.post(
    "/{conta_ig_id}/rag", response_model=FonteRagResponse, status_code=status.HTTP_201_CREATED
)
async def indexar_fonte_rag(
    conta_ig_id: UUID, payload: IndexarFonteRagRequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> FonteRagResponse:
    fonte = await uc.indexar_fonte(
        IndexarFonteRagCmd(
            empresa_id=ctx.empresa_id, conta_ig_id=conta_ig_id,
            tipo=payload.tipo, titulo=payload.titulo, conteudo=payload.conteudo,
        )
    )
    return _to_rag_response(fonte)


@router.delete("/{conta_ig_id}/rag/{fonte_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_fonte_rag(
    conta_ig_id: UUID, fonte_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> None:
    if not await uc.remover_fonte(ctx.empresa_id, conta_ig_id, fonte_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fonte RAG não encontrada."
        )


@router.get("/{conta_ig_id}/orcamento", response_model=ResumoOrcamentoResponse)
async def consultar_orcamento_conta(
    conta_ig_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    prompts_uc: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
    orcamento_uc: Annotated[ServicoOrcamentoUseCase, Depends(obter_orcamento_uc)],
) -> ResumoOrcamentoResponse:
    await prompts_uc.exigir_conta(ctx.empresa_id, conta_ig_id)
    resumo = await orcamento_uc.obter_resumo_mensal(ctx.empresa_id, conta_ig_id)
    return ResumoOrcamentoResponse(
        empresa_id=resumo.empresa_id, conta_ig_id=resumo.conta_ig_id,
        ano=resumo.ano, mes=resumo.mes, limite_mensal_usd=resumo.limite_mensal_usd,
        gasto_empresa_usd=resumo.gasto_empresa_usd, gasto_conta_usd=resumo.gasto_conta_usd,
        saldo_disponivel_usd=resumo.saldo_disponivel_usd,
        percentual_usado=resumo.percentual_usado, bloqueio_orcamento=resumo.bloqueio_orcamento,
    )
