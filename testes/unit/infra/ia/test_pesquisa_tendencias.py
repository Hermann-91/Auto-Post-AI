"""Testes unitários da pesquisa web de tendências e cache 24h a 72h."""

from __future__ import annotations

import json
from typing import Any

import httpx
from redis.exceptions import RedisError

from app.infra.ia.pesquisa_tendencias import (
    BuscadorTendenciasDuckDuckGo,
    CacheTendenciasMemoria,
    CacheTendenciasRedis,
    PesquisaTendenciasAdapter,
)


class _FakeRedis:
    def __init__(self, falhar: bool = False) -> None:
        self.dados: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self._falhar = falhar

    async def get(self, name: str) -> Any:
        if self._falhar:
            raise RedisError("redis offline")
        val = self.dados.get(name)
        return val.encode("utf-8") if val is not None else None

    async def set(self, name: str, value: str, ex: int | None = None) -> Any:
        if self._falhar:
            raise RedisError("redis offline")
        self.dados[name] = value
        self.ttls[name] = ex


async def test_pesquisa_tendencias_usa_cache_memoria_e_limita_ttl_24_72h() -> None:
    chamadas = 0

    def handler(_req: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(
            200,
            json={
                "Heading": "Cafeteria Especial",
                "AbstractText": "Métodos filtrados e drinks gelados em alta.",
                "AbstractURL": "https://exemplo.com/cafe",
                "RelatedTopics": [
                    {"Text": "Matcha artesanal cresce no verão", "FirstURL": "https://ex.com/m"}
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        buscador = BuscadorTendenciasDuckDuckGo(http_client=client)
        adapter = PesquisaTendenciasAdapter(cache=CacheTendenciasMemoria(), buscador=buscador)

        primeiro = await adapter.buscar_tendencias("Cafeteria", "Curitiba", ttl_horas=10)
        segundo = await adapter.buscar_tendencias(" cafeteria ", "curitiba", ttl_horas=100)

    assert chamadas == 1
    assert primeiro["cache_hit"] is False
    assert primeiro["ttl_horas"] == 24
    assert len(primeiro["topicos"]) == 2
    assert segundo["cache_hit"] is True


async def test_pesquisa_tendencias_redis_e_fallback_offline() -> None:
    fake_redis = _FakeRedis()
    cache = CacheTendenciasRedis(fake_redis)

    def handler_erro(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem internet")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_erro)) as client:
        buscador = BuscadorTendenciasDuckDuckGo(http_client=client)
        adapter = PesquisaTendenciasAdapter(cache=cache, buscador=buscador)
        res = await adapter.buscar_tendencias("Moda Sustentável", "SP", ttl_horas=48)

    assert res["fonte"] == "fallback_offline"
    assert len(res["topicos"]) >= 2
    chave = next(iter(fake_redis.dados))
    assert fake_redis.ttls[chave] == 3600
    assert json.loads(fake_redis.dados[chave])["nicho"] == "Moda Sustentável"

    cache_quebrado = CacheTendenciasRedis(_FakeRedis(falhar=True))
    assert await cache_quebrado.obter("x") is None
