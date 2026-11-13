"""Rate limiter distribuído em Redis com execução atômica via Lua."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_SCRIPT_RATE_LIMIT_LUA = """
local atual = redis.call('INCR', KEYS[1])
if atual == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
    ttl = tonumber(ARGV[1])
    redis.call('EXPIRE', KEYS[1], ttl)
end
return {atual, ttl}
"""


class ClienteRedisEvalPort(Protocol):
    """Subconjunto mínimo de cliente Redis assíncrono necessário ao rate limit."""

    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any: ...


class RedisRateLimiter:
    """Controla tentativas distribuídas entre workers com atomicidade Lua."""

    def __init__(
        self,
        redis_client: ClienteRedisEvalPort,
        max_tentativas: int = 5,
        janela_segundos: int = 900,
        fail_closed: bool = True,
    ) -> None:
        self._redis = redis_client
        self._max_tentativas = max_tentativas
        self._janela_segundos = janela_segundos
        self._fail_closed = fail_closed

    async def verificar_e_consumir(self, chave: str) -> tuple[bool, int]:
        """Incrementa contador no Redis e retorna (permitido, retry_after_segundos)."""
        try:
            resultado = await self._redis.eval(
                _SCRIPT_RATE_LIMIT_LUA,
                1,
                chave,
                self._janela_segundos,
            )
            contagem = int(resultado[0])
            ttl = max(1, int(resultado[1]))
            if contagem > self._max_tentativas:
                return False, ttl
            return True, 0
        except RedisError as exc:
            logger.warning("Erro ao consultar Redis no rate limit: %s", type(exc).__name__)
            if self._fail_closed:
                return False, 60
            return True, 0
