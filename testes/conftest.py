"""Fixtures compartilhadas da suíte de testes unitários e de integração."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Configuracoes
from app.core.seguranca.senha_argon2 import Argon2idHasher
from app.infra.seguranca.turnstile_adapter import StubCaptchaAdapter
from app.main import criar_app


@pytest.fixture
def config_teste() -> Configuracoes:
    """Configuração determinística isolada para testes (Argon2 reduzido e sem Redis)."""
    return Configuracoes(
        app_env="test",
        cors_origens=["https://painel.exemplo.com"],
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
        cookie_secure=True,
        captcha_enabled=False,
        rate_limit_max_tentativas=5,
        rate_limit_janela_segundos=60,
    )


@pytest.fixture
def hasher_rapido() -> Argon2idHasher:
    """Instância Argon2id leve para acelerar testes sem perder o algoritmo real."""
    return Argon2idHasher(time_cost=1, memory_cost=8192, parallelism=1)


@pytest.fixture
def app_teste(config_teste: Configuracoes) -> FastAPI:
    """Cria instância limpa da API com estado isolado por teste."""
    return criar_app(config_teste)


@pytest.fixture
async def cliente_http(app_teste: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente HTTPX apontando para HTTPS para validar cookies Secure e HttpOnly."""
    transport = ASGITransport(app=app_teste)
    async with AsyncClient(transport=transport, base_url="https://testserver") as client:
        yield client


def injetar_captcha_stub(app_teste: FastAPI, valido: bool) -> None:
    """Substitui o adaptador de captcha no container da aplicação de teste."""
    container = app_teste.state.auth_container
    container.captcha = StubCaptchaAdapter(sempre_valido=valido)
