"""Testes unitários de LockMemoria e LockRedis em app.infra.seguranca."""

from __future__ import annotations

from typing import Any

from redis.exceptions import RedisError

from app.infra.seguranca.lock_distribuido import LockMemoria, LockRedis


class _FakeRedisLock:
    def __init__(self, falhar: bool = False) -> None:
        self.itens: dict[str, str] = {}
        self.falhar = falhar

    async def set(
        self, name: str, value: str, px: int | None = None, nx: bool = False
    ) -> bool:
        _ = px
        if self.falhar:
            raise RedisError("offline")
        if nx and name in self.itens:
            return False
        self.itens[name] = value
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any:
        _ = (script, numkeys)
        if self.falhar:
            raise RedisError("offline")
        chave, token = str(keys_and_args[0]), str(keys_and_args[1])
        if self.itens.get(chave) == token:
            self.itens.pop(chave, None)
            return 1
        return 0


async def test_lock_distribuido_exclusividade_e_fail_safe() -> None:
    for lock in (LockMemoria(), LockRedis(_FakeRedisLock())):
        tok = await lock.adquirir("k1", 10)
        assert tok is not None
        assert await lock.adquirir("k1", 10) is None
        await lock.liberar("k1", "outro")
        assert await lock.adquirir("k1", 10) is None
        await lock.liberar("k1", tok)
        assert await lock.adquirir("k1", 10) is not None

    assert await LockRedis(_FakeRedisLock(falhar=True)).adquirir("k2", 10) is None
