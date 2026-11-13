"""Ponto de entrada e fábrica da aplicação FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencias.container_auth import construir_container_auth
from app.api.middlewares.seguranca_http import aplicar_headers_seguranca
from app.api.rotas import auth, health
from app.core.config import Configuracoes, obter_configuracoes
from app.core.logging_config import configurar_logging
from app.dominio.excecoes import (
    ErroCaptchaInvalido,
    ErroConflitoDados,
    ErroCotaExcedida,
    ErroCredenciaisInvalidas,
    ErroDominio,
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
}


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


def criar_app(config: Configuracoes | None = None) -> FastAPI:
    """Constrói instância isolada da API FastAPI pronta para produção e testes."""
    configurar_logging()
    cfg = config or obter_configuracoes()
    container = construir_container_auth(cfg)

    @asynccontextmanager
    async def lifespan(aplicacao: FastAPI) -> AsyncIterator[None]:
        aplicacao.state.auth_container = container
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

    aplicacao.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origens,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    aplicacao.middleware("http")(aplicar_headers_seguranca)
    _registrar_handlers_erro(aplicacao)

    aplicacao.include_router(health.router)
    aplicacao.include_router(auth.router)
    return aplicacao


app = criar_app()
