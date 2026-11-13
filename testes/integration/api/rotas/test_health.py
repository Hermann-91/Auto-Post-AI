"""Testes de integração dos endpoints de saúde e headers defensivos."""

from __future__ import annotations

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
