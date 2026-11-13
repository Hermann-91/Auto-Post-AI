"""Adaptadores de cache (memória e Redis) para pesquisa de tendências web."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class CacheTendenciasPort(Protocol):
    async def obter(self, chave: str) -> dict[str, Any] | None: ...
    async def definir(self, chave: str, valor: dict[str, Any], ttl_segundos: int) -> None: ...


class ClienteRedisCachePort(Protocol):
    async def get(self, name: str) -> Any: ...
    async def set(self, name: str, value: str, ex: int | None = None) -> Any: ...


class CacheTendenciasMemoria:
    """Cache TTL em memória para desenvolvimento e testes sem Redis."""

    def __init__(self) -> None:
        self._itens: dict[str, tuple[float, dict[str, Any]]] = {}

    async def obter(self, chave: str) -> dict[str, Any] | None:
        entrada = self._itens.get(chave)
        if entrada is None:
            return None
        expira_em, payload = entrada
        if time.monotonic() >= expira_em:
            self._itens.pop(chave, None)
            return None
        return dict(payload)

    async def definir(self, chave: str, valor: dict[str, Any], ttl_segundos: int) -> None:
        self._itens[chave] = (time.monotonic() + ttl_segundos, dict(valor))


class CacheTendenciasRedis:
    """Cache distribuído no Redis com fallback silencioso para cache miss."""

    def __init__(self, redis_client: ClienteRedisCachePort) -> None:
        self._redis = redis_client

    async def obter(self, chave: str) -> dict[str, Any] | None:
        try:
            bruto = await self._redis.get(chave)
            if not bruto:
                return None
            texto = bruto.decode("utf-8") if isinstance(bruto, bytes) else str(bruto)
            dados = json.loads(texto)
            return dict(dados) if isinstance(dados, dict) else None
        except (RedisError, ValueError) as exc:
            logger.warning("Falha ao ler cache Redis de tendências: %s", type(exc).__name__)
            return None

    async def definir(self, chave: str, valor: dict[str, Any], ttl_segundos: int) -> None:
        try:
            serializado = json.dumps(valor, ensure_ascii=False)
            await self._redis.set(chave, serializado, ex=ttl_segundos)
        except RedisError as exc:
            logger.warning("Falha ao gravar cache Redis de tendências: %s", type(exc).__name__)
