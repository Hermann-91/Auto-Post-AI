"""Headers HTTP defensivos e validação de origem contra CSRF em cookies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response, status

from app.core.config import Configuracoes


def _extrair_origem(url_bruta: str) -> str:
    analisada = urlparse(url_bruta)
    if not analisada.scheme or not analisada.netloc:
        return ""
    return f"{analisada.scheme.lower()}://{analisada.netloc.lower()}"


async def aplicar_headers_seguranca(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Injeta cabeçalhos de proteção contra clickjacking, MIME sniffing e cache."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/auth"):
        response.headers["Cache-Control"] = "no-store"
    return response


def validar_origem_csrf(request: Request, config: Configuracoes) -> None:
    """Valida Origin/Referer quando a requisição POST carrega cookies de sessão."""
    possui_cookie = (
        config.cookie_access_nome in request.cookies
        or config.cookie_refresh_nome in request.cookies
    )
    if not possui_cookie:
        return

    origem_header = request.headers.get("origin") or request.headers.get("referer")
    if not origem_header:
        return

    origem_req = _extrair_origem(origem_header)
    origem_propria = _extrair_origem(str(request.base_url))
    permitidas = {_extrair_origem(item) for item in config.cors_origens}
    permitidas.add(origem_propria)

    if origem_req not in permitidas:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origem da requisição não autorizada.",
        )
