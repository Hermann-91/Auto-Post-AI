"""Headers HTTP defensivos e validação de origem contra CSRF em cookies."""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.config import Configuracoes

_METODOS_MUTAVEIS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_ROTAS_PUBLICAS_AUTH = frozenset({"/auth/login", "/auth/register"})
_CSP_POLITICA = (
    "default-src 'self'; "
    "script-src 'self' https://challenges.cloudflare.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https: http://localhost:*; "
    "media-src 'self' blob: https: http://localhost:*; "
    "frame-src https://challenges.cloudflare.com; "
    "connect-src 'self' https://challenges.cloudflare.com; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def _extrair_origem(url_bruta: str) -> str:
    analisada = urlparse(url_bruta)
    if not analisada.scheme or not analisada.netloc:
        return ""
    return f"{analisada.scheme.lower()}://{analisada.netloc.lower()}"


async def aplicar_headers_seguranca(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Aplica proteção CSRF global em mutações e cabeçalhos HTTP defensivos."""
    container = getattr(request.app.state, "auth_container", None)
    if request.method in _METODOS_MUTAVEIS and container is not None:
        try:
            validar_origem_csrf(request, container.config)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = _CSP_POLITICA
    if container is not None and container.config.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/auth"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _validar_double_submit_csrf(request: Request, config: Configuracoes) -> None:
    cookie_csrf = request.cookies.get(config.cookie_csrf_nome, "").strip()
    header_csrf = request.headers.get("x-csrf-token", "").strip()
    em_navegador = bool(request.headers.get("origin") or request.headers.get("sec-fetch-site"))
    eh_publica = request.url.path in _ROTAS_PUBLICAS_AUTH
    exigir = bool(header_csrf) or (bool(cookie_csrf) and em_navegador and not eh_publica)
    valido = bool(cookie_csrf and header_csrf) and hmac.compare_digest(cookie_csrf, header_csrf)
    if exigir and not valido:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF ausente ou inválido.",
        )


def validar_origem_csrf(request: Request, config: Configuracoes) -> None:
    """Valida Origin/Referer, Sec-Fetch-Site e CSRF quando a requisição usa cookies."""
    possui_cookie = (
        config.cookie_access_nome in request.cookies
        or config.cookie_refresh_nome in request.cookies
    )
    if not possui_cookie:
        return

    origem_propria = _extrair_origem(str(request.base_url))
    permitidas = {_extrair_origem(item) for item in config.cors_origens}
    permitidas.add(origem_propria)

    sec_fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    origem_header = request.headers.get("origin") or request.headers.get("referer")
    if sec_fetch_site == "cross-site" and not origem_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requisição cross-site não autorizada.",
        )

    if origem_header:
        origem_req = _extrair_origem(origem_header)
        if origem_req not in permitidas:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Origem da requisição não autorizada.",
            )

    _validar_double_submit_csrf(request, config)
