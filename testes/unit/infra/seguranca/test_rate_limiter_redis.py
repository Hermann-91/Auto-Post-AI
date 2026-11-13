"""Testes unitários de RedisRateLimiter com cliente Redis simulado."""

from __future__ import annotations

from typing import Any

from redis.exceptions import RedisError

from app.infra.seguranca.rate_limiter_redis import RedisRateLimiter


class _FakeRedisEval:
    def __init__(self, contagem: int = 1, ttl: int = 900, falhar: bool = False) -> None:
        self.contagem = contagem
        self.ttl = ttl
        self.falhar = falhar

    async def eval(self, _script: str, _numkeys: int, *_args: Any) -> list[int]:
        if self.falhar:
            raise RedisError("Conexão recusada")
        return [self.contagem, self.ttl]


async def test_redis_rate_limiter_permite_bloqueia_e_aplica_fail_closed() -> None:
    ok_limiter = RedisRateLimiter(_FakeRedisEval(contagem=5, ttl=120), max_tentativas=5)
    assert await ok_limiter.verificar_e_consumir("rl:test") == (True, 0)

    bloq_limiter = RedisRateLimiter(_FakeRedisEval(contagem=6, ttl=120), max_tentativas=5)
    assert await bloq_limiter.verificar_e_consumir("rl:test") == (False, 120)

    erro_limiter = RedisRateLimiter(_FakeRedisEval(falhar=True), fail_closed=True)
    assert await erro_limiter.verificar_e_consumir("rl:test") == (False, 60)
