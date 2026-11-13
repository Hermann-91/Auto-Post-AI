"""Dependências de resolução de identidade e tenant a partir do JWT."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.api.dependencias.container_auth import ContainerAuth, obter_container_auth
from app.dominio.excecoes import ErroCredenciaisInvalidas
from app.dominio.objetos_valor.enums_tenant import PapelUsuario
from app.dominio.portas.seguranca import PayloadAccessToken


def _extrair_token_requisicao(request: Request, nome_cookie: str) -> str:
    autorizacao = request.headers.get("authorization", "")
    if autorizacao.lower().startswith("bearer "):
        token_bearer = autorizacao[7:].strip()
        if token_bearer:
            return token_bearer

    token_cookie = request.cookies.get(nome_cookie, "").strip()
    if token_cookie:
        return token_cookie

    raise ErroCredenciaisInvalidas("Autenticação obrigatória.")


def obter_usuario_atual(
    request: Request,
    container: Annotated[ContainerAuth, Depends(obter_container_auth)],
) -> PayloadAccessToken:
    """Decodifica o JWT da sessão garantindo empresa_id confiável do servidor."""
    token = _extrair_token_requisicao(request, container.config.cookie_access_nome)
    return container.tokens.decodificar_access_token(token)


def exigir_papel_admin(
    usuario: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
) -> PayloadAccessToken:
    """Restringe endpoints administrativos a usuários com papel ADMIN."""
    if usuario.papel != PapelUsuario.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissão administrativa necessária.",
        )
    return usuario
