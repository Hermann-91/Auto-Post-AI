"""Ponto de entrada e fábrica da aplicação FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.dependencias.container_auth import construir_container_auth
from app.api.dependencias.container_ia import construir_container_ia
from app.api.dependencias.container_meta import construir_container_meta
from app.api.dependencias.container_servicos import construir_container_servicos
from app.api.middlewares.seguranca_http import aplicar_headers_seguranca
from app.api.rotas import (
    auth,
    biblioteca,
    contas_config,
    criacao,
    health,
    meta_oauth,
    midia_publica,
    planejamento,
    posts,
)
from app.core.config import Configuracoes, obter_configuracoes
from app.core.logging_config import configurar_logging
from app.dominio.excecoes import (
    ErroCaptchaInvalido,
    ErroConflitoDados,
    ErroCotaExcedida,
    ErroCredenciaisInvalidas,
    ErroDominio,
    ErroIntegracaoIA,
    ErroIntegracaoMeta,
    ErroLimitePublicacaoMeta,
    ErroOrcamentoExcedido,
    ErroRateLimitExcedido,
    ErroTokenReutilizado,
    ErroTransicaoEstado,
    ErroValidacaoDominio,
)

_MAPA_STATUS_DOMINIO: dict[type[ErroDominio], int] = {
    ErroCredenciaisInvalidas: status.HTTP_401_UNAUTHORIZED,
    ErroTokenReutilizado: status.HTTP_401_UNAUTHORIZED,
    ErroCaptchaInvalido: status.HTTP_403_FORBIDDEN,
    ErroConflitoDados: status.HTTP_409_CONFLICT,
    ErroValidacaoDominio: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErroTransicaoEstado: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErroCotaExcedida: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErroOrcamentoExcedido: status.HTTP_402_PAYMENT_REQUIRED,
    ErroIntegracaoIA: status.HTTP_502_BAD_GATEWAY,
    ErroIntegracaoMeta: status.HTTP_502_BAD_GATEWAY,
    ErroLimitePublicacaoMeta: status.HTTP_429_TOO_MANY_REQUESTS,
}

_DIR_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def _registrar_handlers_erro(app: FastAPI) -> None:
    @app.exception_handler(ErroRateLimitExcedido)
    async def _tratar_rate_limit(
        _request: Request,
        exc: ErroRateLimitExcedido,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": str(exc)},
            headers={"Retry-After": str(exc.retry_after_segundos)},
        )

    @app.exception_handler(ErroDominio)
    async def _tratar_erro_dominio(_request: Request, exc: ErroDominio) -> JSONResponse:
        codigo = _MAPA_STATUS_DOMINIO.get(type(exc), status.HTTP_400_BAD_REQUEST)
        return JSONResponse(status_code=codigo, content={"detail": str(exc)})


def _montar_frontend(aplicacao: FastAPI) -> None:
    if not _DIR_FRONTEND.is_dir():
        return
    if (_DIR_FRONTEND / "css").is_dir():
        aplicacao.mount("/painel/css", StaticFiles(directory=_DIR_FRONTEND / "css"), name="css")
    if (_DIR_FRONTEND / "js").is_dir():
        aplicacao.mount("/painel/js", StaticFiles(directory=_DIR_FRONTEND / "js"), name="js")

    @aplicacao.get("/", include_in_schema=False)
    async def redirecionar_raiz() -> RedirectResponse:
        return RedirectResponse(url="/painel/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @aplicacao.get("/painel", include_in_schema=False)
    @aplicacao.get("/painel/", include_in_schema=False)
    async def servir_painel_spa() -> FileResponse:
        return FileResponse(_DIR_FRONTEND / "index.html")


def criar_app(config: Configuracoes | None = None) -> FastAPI:
    """Constrói instância isolada da API FastAPI pronta para produção e testes."""
    configurar_logging()
    cfg = config or obter_configuracoes()
    container = construir_container_auth(cfg)
    ia_container = construir_container_ia(cfg, container)
    meta_container = construir_container_meta(cfg, container, ia_container)
    servicos_container = construir_container_servicos(cfg)

    @asynccontextmanager
    async def lifespan(aplicacao: FastAPI) -> AsyncIterator[None]:
        aplicacao.state.auth_container = container
        aplicacao.state.ia_container = ia_container
        aplicacao.state.meta_container = meta_container
        aplicacao.state.servicos_container = servicos_container
        try:
            yield
        finally:
            await container.fechar()

    aplicacao = FastAPI(
        title=cfg.app_nome,
        version="0.1.0",
        lifespan=lifespan,
    )
    aplicacao.state.auth_container = container
    aplicacao.state.ia_container = ia_container
    aplicacao.state.meta_container = meta_container
    aplicacao.state.servicos_container = servicos_container

    aplicacao.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origens,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )
    aplicacao.middleware("http")(aplicar_headers_seguranca)
    _registrar_handlers_erro(aplicacao)

    aplicacao.include_router(health.router)
    aplicacao.include_router(auth.router)
    aplicacao.include_router(contas_config.router)
    aplicacao.include_router(criacao.router)
    aplicacao.include_router(planejamento.router)
    aplicacao.include_router(meta_oauth.router)
    aplicacao.include_router(posts.router)
    aplicacao.include_router(biblioteca.router)
    aplicacao.include_router(midia_publica.router)
    _montar_frontend(aplicacao)
    return aplicacao


app = criar_app()
