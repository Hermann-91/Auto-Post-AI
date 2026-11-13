"""Testes unitários da barreira GuardiaoEntradaAuth."""

from __future__ import annotations

import pytest

from app.aplicacao.auth.protecao_entrada import GuardiaoEntradaAuth
from app.dominio.excecoes import ErroCaptchaInvalido, ErroRateLimitExcedido
from app.infra.seguranca.rate_limiter_mem import InMemoryRateLimiter


class _SpyCaptcha:
    def __init__(self, resultado: bool = True) -> None:
        self.chamadas = 0
        self.resultado = resultado

    async def verificar(self, token_captcha: str, ip_remoto: str | None) -> bool:
        self.chamadas += 1
        return self.resultado


async def test_rate_limit_bloqueia_antes_do_turnstile_e_chave_sem_pii() -> None:
    limiter = InMemoryRateLimiter(max_tentativas=1, janela_segundos=60)
    captcha = _SpyCaptcha(resultado=True)
    guardiao = GuardiaoEntradaAuth(rate_limiter=limiter, captcha=captcha)

    await guardiao.validar_entrada("Cliente@Teste.com", "tok", "1.2.3.4", "login")
    assert captcha.chamadas == 1

    with pytest.raises(ErroRateLimitExcedido) as exc:
        await guardiao.validar_entrada("cliente@teste.com", "tok", "1.2.3.4", "login")
    assert exc.value.retry_after_segundos >= 1
    assert captcha.chamadas == 1


async def test_turnstile_invalido_lanca_erro() -> None:
    guardiao = GuardiaoEntradaAuth(
        rate_limiter=InMemoryRateLimiter(max_tentativas=5, janela_segundos=60),
        captcha=_SpyCaptcha(resultado=False),
    )
    with pytest.raises(ErroCaptchaInvalido):
        await guardiao.validar_entrada("a@b.com", "bad", "1.2.3.4", "login")
