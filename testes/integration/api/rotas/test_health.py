"""Testes de integração dos endpoints de saúde e headers defensivos."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient


async def test_healthz_e_headers_de_seguranca(cliente_http: AsyncClient) -> None:
    resp = await cliente_http.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"

    ready = await cliente_http.get("/readyz")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


async def test_readyz_retorna_503_quando_redis_falha(
    app_teste: FastAPI,
    cliente_http: AsyncClient,
) -> None:
    class _RedisQuebrado:
        async def ping(self) -> bool:
            raise ConnectionError("Redis offline")

    app_teste.state.auth_container.redis_client = _RedisQuebrado()
    resp = await cliente_http.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unready"}
