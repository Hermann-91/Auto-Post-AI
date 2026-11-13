"""Locks distribuídos em Redis e memória para coordenação segura entre API e Worker."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Protocol

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_SCRIPT_LIBERAR_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class ClienteRedisLockPort(Protocol):
    """Subconjunto mínimo do cliente Redis para aquisição e liberação atômica."""

    async def set(
        self,
        name: str,
        value: str,
        px: int | None = None,
        nx: bool = False,
    ) -> Any: ...
    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any: ...


class LockMemoria:
    """Lock em memória com TTL por monotonic clock para desenvolvimento e testes."""

    def __init__(self) -> None:
        self._locks: dict[str, tuple[str, float]] = {}
        self._mutex = asyncio.Lock()

    async def adquirir(self, chave: str, ttl_segundos: int) -> str | None:
        async with self._mutex:
            agora = time.monotonic()
            atual = self._locks.get(chave)
            if atual is not None and atual[1] > agora:
                return None
            token = uuid.uuid4().hex
            self._locks[chave] = (token, agora + max(1, ttl_segundos))
            return token

    async def liberar(self, chave: str, token_lock: str) -> None:
        async with self._mutex:
            atual = self._locks.get(chave)
            if atual is not None and atual[0] == token_lock:
                self._locks.pop(chave, None)


class LockRedis:
    """Lock distribuído no Redis com verificação de ownership na liberação."""

    def __init__(self, redis_client: ClienteRedisLockPort, prefixo: str = "lock:") -> None:
        self._redis = redis_client
        self._prefixo = prefixo

    async def adquirir(self, chave: str, ttl_segundos: int) -> str | None:
        token = uuid.uuid4().hex
        ttl_ms = max(1000, ttl_segundos * 1000)
        try:
            ok = await self._redis.set(f"{self._prefixo}{chave}", token, px=ttl_ms, nx=True)
            return token if ok else None
        except RedisError as exc:
            logger.warning("Falha ao adquirir lock Redis (%s): %s", chave, type(exc).__name__)
            return None

    async def liberar(self, chave: str, token_lock: str) -> None:
        try:
            await self._redis.eval(
                _SCRIPT_LIBERAR_LOCK_LUA, 1, f"{self._prefixo}{chave}", token_lock
            )
        except RedisError as exc:
            logger.warning("Falha ao liberar lock Redis (%s): %s", chave, type(exc).__name__)
