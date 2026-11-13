"""Rotas HTTP para conexão OAuth oficial Instagram Login e renovação de tokens."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencias.provedores_meta import obter_oauth_meta_uc
from app.api.dependencias.usuario_atual import obter_usuario_atual
from app.api.schemas.postagens_meta import (
    ContaMetaConectadaResponse,
    UrlOAuthMetaResponse,
)
from app.aplicacao.publicacao import ConectarMetaCallbackCmd, ServicoOAuthMetaUseCase
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroIntegracaoMeta, ErroValidacaoDominio
from app.dominio.portas.seguranca import PayloadAccessToken

router = APIRouter(prefix="/meta", tags=["meta-oauth"])


def _to_conta_response(conta: ContaInstagram) -> ContaMetaConectadaResponse:
    return ContaMetaConectadaResponse(
        id=conta.id,
        empresa_id=conta.empresa_id,
        ig_user_id=conta.ig_user_id,
        username=conta.username,
        provedor=conta.provedor,
        ativa=conta.ativa,
        token_expira_em=conta.token_expira_em,
    )


@router.get("/oauth/url", response_model=UrlOAuthMetaResponse)
async def obter_url_autorizacao_meta(
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoOAuthMetaUseCase, Depends(obter_oauth_meta_uc)],
) -> UrlOAuthMetaResponse:
    """Gera URL de consentimento da Meta vinculada ao usuário e empresa."""
    url, state = await uc.iniciar_autorizacao(ctx.empresa_id, ctx.usuario_id)
    return UrlOAuthMetaResponse(url_autorizacao=url, state=state)


@router.get("/oauth/callback", response_model=ContaMetaConectadaResponse)
async def callback_oauth_meta(
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoOAuthMetaUseCase, Depends(obter_oauth_meta_uc)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
) -> ContaMetaConectadaResponse:
    """Conclui OAuth trocando code por Long-Lived Token criptografado."""
    if error:
        detalhe = error_description or error
        raise ErroIntegracaoMeta(f"Autorização Meta cancelada ou negada: {detalhe}")
    if not code or not state:
        raise ErroValidacaoDominio("Parâmetros code e state são obrigatórios no callback.")
    conta = await uc.concluir_callback(
        ConectarMetaCallbackCmd(
            empresa_id=ctx.empresa_id,
            usuario_id=ctx.usuario_id,
            codigo=code,
            state=state,
        )
    )
    return _to_conta_response(conta)


@router.post("/contas/{conta_ig_id}/renovar-token", response_model=ContaMetaConectadaResponse)
async def renovar_token_conta_meta(
    conta_ig_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoOAuthMetaUseCase, Depends(obter_oauth_meta_uc)],
) -> ContaMetaConectadaResponse:
    """Renova manualmente o Long-Lived Token da conta Instagram autenticada."""
    conta = await uc.renovar_token_conta(ctx.empresa_id, conta_ig_id)
    return _to_conta_response(conta)
