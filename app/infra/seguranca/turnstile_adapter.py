"""Adaptadores de verificação anti-bot (Cloudflare Turnstile e Stub Dev)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CloudflareTurnstileAdapter:
    """Valida token Turnstile na API oficial da Cloudflare com timeout estrito."""

    def __init__(
        self,
        secret_key: str,
        verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        timeout_segundos: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not secret_key.strip():
            raise ValueError("TURNSTILE_SECRET_KEY não pode ser vazia.")
        self._secret_key = secret_key
        self._verify_url = verify_url
        self._timeout = timeout_segundos
        self._http_client = http_client

    async def verificar(self, token_captcha: str, ip_remoto: str | None) -> bool:
        """Consulta endpoint siteverify; retorna False em qualquer erro ou falha."""
        if not token_captcha.strip():
            return False

        payload: dict[str, str] = {
            "secret": self._secret_key,
            "response": token_captcha.strip(),
        }
        if ip_remoto:
            payload["remoteip"] = ip_remoto

        try:
            dados = await self._enviar_requisicao(payload)
            return bool(dados.get("success", False))
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede ao consultar Turnstile: %s", type(exc).__name__)
            return False

    async def _enviar_requisicao(self, payload: dict[str, str]) -> dict[str, Any]:
        if self._http_client is not None:
            resp = await self._http_client.post(self._verify_url, data=payload)
            resp.raise_for_status()
            return dict(resp.json())

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._verify_url, data=payload)
            resp.raise_for_status()
            return dict(resp.json())


class StubCaptchaAdapter:
    """Adaptador controlado por DI para ambiente dev/test quando captcha está desligado."""

    def __init__(self, sempre_valido: bool = True, token_esperado: str | None = None) -> None:
        self._sempre_valido = sempre_valido
        self._token_esperado = token_esperado

    async def verificar(self, token_captcha: str, ip_remoto: str | None) -> bool:
        """Retorna resultado determinístico sem chamadas externas."""
        if self._token_esperado is not None:
            return token_captcha == self._token_esperado
        return self._sempre_valido
