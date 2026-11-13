"""Testes de integração de locks distribuídos e store de states OAuth."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from app.dominio.excecoes import ErroIntegracaoMeta
from app.infra.meta.state_oauth_store import StateOAuthMemoria, StateOAuthRedis
from app.worker.locks import LockMemoria, LockRedis


class _FakeRedis:
    def __init__(self, falhar: bool = False) -> None:
        self.dados: dict[str, str] = {}
        self.falhar = falhar

    async def set(
        self,
        name: str,
        value: str,
        px: int | None = None,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        _ = (px, ex)
        if self.falhar:
            raise RedisError("Redis offline")
        if nx and name in self.dados:
            return False
        self.dados[name] = value
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any:
        _ = numkeys
        if self.falhar:
            raise RedisError("Redis offline")
        chave = str(keys_and_args[0])
        if "DEL" in script and len(keys_and_args) == 2:
            if self.dados.get(chave) == str(keys_and_args[1]):
                self.dados.pop(chave, None)
                return 1
            return 0
        return self.dados.pop(chave, None)


async def test_lock_memoria_e_redis_exclusividade_e_ownership() -> None:
    for lock in (LockMemoria(), LockRedis(_FakeRedis())):
        t1 = await lock.adquirir("post:1", 30)
        assert t1 is not None
        assert await lock.adquirir("post:1", 30) is None
        await lock.liberar("post:1", "token_errado")
        assert await lock.adquirir("post:1", 30) is None
        await lock.liberar("post:1", t1)
        assert await lock.adquirir("post:1", 30) is not None

    lock_off = LockRedis(_FakeRedis(falhar=True))
    assert await lock_off.adquirir("post:2", 30) is None


async def test_state_oauth_store_one_time_e_falha_redis() -> None:
    emp, usr = uuid4(), uuid4()
    for store in (StateOAuthMemoria(), StateOAuthRedis(_FakeRedis())):
        await store.salvar_state("st_1", emp, usr, ttl_segundos=60)
        assert await store.consumir_state("st_1") == (emp, usr)
        assert await store.consumir_state("st_1") is None

    store_off = StateOAuthRedis(_FakeRedis(falhar=True))
    with pytest.raises(ErroIntegracaoMeta):
        await store_off.salvar_state("st_2", emp, usr, 60)
