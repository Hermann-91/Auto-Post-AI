"""Testes unitários de InMemoryRateLimiter."""

from __future__ import annotations

from app.infra.seguranca.rate_limiter_mem import InMemoryRateLimiter


async def test_janela_deslizante_bloqueia_e_libera_apos_expirar() -> None:
    tempo = [100.0]
    limiter = InMemoryRateLimiter(max_tentativas=2, janela_segundos=60, relogio=lambda: tempo[0])

    assert await limiter.verificar_e_consumir("k1") == (True, 0)
    assert await limiter.verificar_e_consumir("k1") == (True, 0)

    permitido, retry = await limiter.verificar_e_consumir("k1")
    assert permitido is False
    assert retry == 60

    tempo[0] = 161.0
    assert await limiter.verificar_e_consumir("k1") == (True, 0)
