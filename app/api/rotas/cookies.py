"""Helpers HTTP para gravação e limpeza segura de cookies de sessão e CSRF."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Request, Response

from app.api.dependencias.container_auth import obter_config_app
from app.api.middlewares.seguranca_http import validar_origem_csrf
from app.aplicacao.auth import ParTokensDTO
from app.core.config import Configuracoes


def extrair_ip_cliente(request: Request) -> str | None:
    """Extrai o IP remoto da requisição."""
    return request.client.host if request.client else None


def checar_csrf_cookie(
    request: Request,
    config: Annotated[Configuracoes, Depends(obter_config_app)],
) -> None:
    """Dependência explícita de checagem CSRF."""
    validar_origem_csrf(request, config)


def gravar_cookie_csrf(response: Response, cfg: Configuracoes) -> str:
    """Emite cookie csrf_token legível pelo painel web no mesmo domínio."""
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=cfg.cookie_csrf_nome,
        value=token,
        max_age=cfg.refresh_token_dias * 86400,
        httponly=False,
        secure=cfg.cookie_secure,
        samesite=cfg.cookie_samesite,
        path="/",
    )
    return token


def gravar_cookies_sessao(
    response: Response,
    tokens: ParTokensDTO,
    cfg: Configuracoes,
) -> None:
    """Grava cookies HttpOnly de acesso/refresh e token CSRF pareado."""
    response.set_cookie(
        key=cfg.cookie_access_nome,
        value=tokens.access_token,
        max_age=cfg.access_token_minutos * 60,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite=cfg.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=cfg.cookie_refresh_nome,
        value=tokens.refresh_token,
        max_age=cfg.refresh_token_dias * 86400,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite=cfg.cookie_samesite,
        path="/auth",
    )
    gravar_cookie_csrf(response, cfg)


def limpar_cookies_sessao(response: Response, cfg: Configuracoes) -> None:
    """Remove os cookies de sessão e CSRF do navegador."""
    response.delete_cookie(
        key=cfg.cookie_access_nome,
        path="/",
        httponly=True,
        secure=cfg.cookie_secure,
        samesite=cfg.cookie_samesite,
    )
    response.delete_cookie(
        key=cfg.cookie_refresh_nome,
        path="/auth",
        httponly=True,
        secure=cfg.cookie_secure,
        samesite=cfg.cookie_samesite,
    )
    response.delete_cookie(
        key=cfg.cookie_csrf_nome,
        path="/",
        httponly=False,
        secure=cfg.cookie_secure,
        samesite=cfg.cookie_samesite,
    )
