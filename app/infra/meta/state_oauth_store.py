"""Armazenamento one-time de state OAuth Meta (Memória e Redis atômico)."""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol
from uuid import UUID

from redis.exceptions import RedisError

from app.dominio.excecoes import ErroIntegracaoMeta

logger = logging.getLogger(__name__)

_SCRIPT_CONSUMIR_STATE_LUA = """
local val = redis.call('GET', KEYS[1])
if val then
    redis.call('DEL', KEYS[1])
end
return val
"""


class ClienteRedisStatePort(Protocol):
    """Subconjunto mínimo do Redis assíncrono para states OAuth efêmeros."""

    async def set(self, name: str, value: str, ex: int | None = None) -> Any: ...
    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any: ...


class StateOAuthMemoria:
    """Armazena states OAuth em memória com expiração por monotonic clock."""

    def __init__(self) -> None:
        self._itens: dict[str, tuple[UUID, UUID, float]] = {}

    async def salvar_state(
        self,
        state: str,
        empresa_id: UUID,
        usuario_id: UUID,
        ttl_segundos: int = 600,
    ) -> None:
        expira = time.monotonic() + max(30, ttl_segundos)
        self._itens[state] = (empresa_id, usuario_id, expira)

    async def consumir_state(self, state: str) -> tuple[UUID, UUID] | None:
        registro = self._itens.pop(state, None)
        if registro is None:
            return None
        empresa_id, usuario_id, expira = registro
        if time.monotonic() > expira:
            return None
        return empresa_id, usuario_id


class StateOAuthRedis:
    """Armazena e consome state OAuth no Redis em operação única (Lua GET+DEL)."""

    def __init__(
        self,
        redis_client: ClienteRedisStatePort,
        prefixo: str = "meta:oauth:",
    ) -> None:
        self._redis = redis_client
        self._prefixo = prefixo

    async def salvar_state(
        self,
        state: str,
        empresa_id: UUID,
        usuario_id: UUID,
        ttl_segundos: int = 600,
    ) -> None:
        chave = f"{self._prefixo}{state}"
        valor = f"{empresa_id}|{usuario_id}"
        try:
            await self._redis.set(chave, valor, ex=max(30, ttl_segundos))
        except RedisError as exc:
            logger.warning("Erro ao salvar state OAuth no Redis: %s", type(exc).__name__)
            raise ErroIntegracaoMeta(
                "Serviço de estado OAuth temporariamente indisponível."
            ) from exc

    async def consumir_state(self, state: str) -> tuple[UUID, UUID] | None:
        chave = f"{self._prefixo}{state}"
        try:
            bruto = await self._redis.eval(_SCRIPT_CONSUMIR_STATE_LUA, 1, chave)
        except RedisError as exc:
            logger.warning("Erro ao consumir state OAuth no Redis: %s", type(exc).__name__)
            raise ErroIntegracaoMeta("Falha ao validar estado OAuth no servidor.") from exc
        if not bruto:
            return None
        texto = bruto.decode("utf-8") if isinstance(bruto, bytes) else str(bruto)
        partes = texto.split("|", 1)
        if len(partes) != 2:
            return None
        try:
            return UUID(partes[0]), UUID(partes[1])
        except ValueError:
            return None
