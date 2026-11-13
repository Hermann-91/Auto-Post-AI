"""Barreira compartilhada de Rate Limit e Turnstile para rotas de entrada."""

from __future__ import annotations

import hashlib

from app.dominio.excecoes import ErroCaptchaInvalido, ErroRateLimitExcedido
from app.dominio.portas.seguranca import CaptchaPort, RateLimiterPort


class GuardiaoEntradaAuth:
    """Impõe Rate Limit (IP + hash do e-mail) seguido de validação Turnstile."""

    def __init__(self, rate_limiter: RateLimiterPort, captcha: CaptchaPort) -> None:
        self._rate_limiter = rate_limiter
        self._captcha = captcha

    async def validar_entrada(
        self,
        email: str,
        token_captcha: str,
        ip_remoto: str | None,
        escopo: str,
    ) -> None:
        """Executa checagens na ordem estrita antes do Argon2id."""
        chave = self._montar_chave(email=email, ip_remoto=ip_remoto, escopo=escopo)
        permitido, retry_after = await self._rate_limiter.verificar_e_consumir(chave)
        if not permitido:
            raise ErroRateLimitExcedido(
                "Muitas tentativas. Aguarde antes de tentar novamente.",
                retry_after_segundos=retry_after,
            )

        captcha_valido = await self._captcha.verificar(token_captcha, ip_remoto)
        if not captcha_valido:
            raise ErroCaptchaInvalido("Verificação anti-bot (Turnstile) inválida.")

    @staticmethod
    def _montar_chave(email: str, ip_remoto: str | None, escopo: str) -> str:
        email_norm = email.strip().lower()
        email_hash = hashlib.sha256(email_norm.encode("utf-8")).hexdigest()[:24]
        ip_seguro = (ip_remoto or "desconhecido").strip()
        return f"rl:{escopo}:{ip_seguro}:{email_hash}"
