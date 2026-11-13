"""Testes unitários dos adaptadores de verificação Cloudflare Turnstile."""

from __future__ import annotations

import httpx

from app.infra.seguranca.turnstile_adapter import (
    CloudflareTurnstileAdapter,
    StubCaptchaAdapter,
)


async def test_turnstile_retorna_true_e_false_conforme_siteverify() -> None:
    def _handler_ok(request: httpx.Request) -> httpx.Response:
        assert "secret=segredo" in request.content.decode("utf-8")
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler_ok)) as client:
        adapter = CloudflareTurnstileAdapter(secret_key="segredo", http_client=client)
        assert await adapter.verificar("token-valido", "1.1.1.1") is True
        assert await adapter.verificar("   ", "1.1.1.1") is False


async def test_turnstile_retorna_false_em_erro_http() -> None:
    def _handler_erro(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"success": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler_erro)) as client:
        adapter = CloudflareTurnstileAdapter(secret_key="segredo", http_client=client)
        assert await adapter.verificar("tok", None) is False


async def test_stub_captcha_adapter() -> None:
    assert await StubCaptchaAdapter(token_esperado="1x0000").verificar("1x0000", None) is True
    assert await StubCaptchaAdapter(token_esperado="1x0000").verificar("outro", None) is False
