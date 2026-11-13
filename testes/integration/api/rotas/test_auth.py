"""Testes de integração das rotas /auth/*, cookies seguros e proteções."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from testes.conftest import injetar_captcha_stub


async def test_fluxo_completo_register_me_refresh_e_logout(cliente_http: AsyncClient) -> None:
    reg = await cliente_http.post(
        "/auth/register",
        json={
            "nome_empresa": "Marca Teste",
            "email": "fundador@marca.com",
            "senha": "SenhaSuperSegura#1",
            "turnstile_token": "ok",
        },
    )
    assert reg.status_code == 201
    assert reg.headers["cache-control"] == "no-store"
    assert "access_token" in cliente_http.cookies
    assert "refresh_token" in cliente_http.cookies

    me = await cliente_http.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "fundador@marca.com"
    assert me.json()["papel"] == "ADMIN"

    ref = await cliente_http.post("/auth/refresh")
    assert ref.status_code == 200

    out = await cliente_http.post("/auth/logout")
    assert out.status_code == 200

    me_apos_logout = await cliente_http.get("/auth/me")
    assert me_apos_logout.status_code == 401


async def test_bloqueia_mass_assignment_csrf_turnstile_e_rate_limit(
    app_teste: FastAPI,
    cliente_http: AsyncClient,
) -> None:
    # 1. Mass assignment bloqueado pelo schema (extra="forbid")
    mass = await cliente_http.post(
        "/auth/register",
        json={
            "nome_empresa": "X",
            "email": "x@x.com",
            "senha": "SenhaValida123",
            "papel": "ADMIN",
            "empresa_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert mass.status_code == 422

    # 2. Turnstile inválido -> 403
    injetar_captcha_stub(app_teste, valido=False)
    cap = await cliente_http.post(
        "/auth/login",
        json={"email": "a@b.com", "senha": "123", "turnstile_token": "bad"},
    )
    assert cap.status_code == 403

    # 3. Rate limit (5 tentativas na 6a retorna 429 + Retry-After)
    injetar_captcha_stub(app_teste, valido=True)
    for _ in range(4):
        await cliente_http.post(
            "/auth/login",
            json={"email": "a@b.com", "senha": "123", "turnstile_token": "ok"},
        )
    bloq = await cliente_http.post(
        "/auth/login",
        json={"email": "a@b.com", "senha": "123", "turnstile_token": "ok"},
    )
    assert bloq.status_code == 429
    assert int(bloq.headers["retry-after"]) >= 1


async def test_refresh_rejeita_origem_csrf_nao_autorizada(cliente_http: AsyncClient) -> None:
    await cliente_http.post(
        "/auth/register",
        json={
            "nome_empresa": "CSRF Co",
            "email": "csrf@co.com",
            "senha": "SenhaSuperSegura#1",
            "turnstile_token": "ok",
        },
    )
    resp = await cliente_http.post(
        "/auth/refresh",
        headers={"Origin": "https://site-malicioso.evil"},
    )
    assert resp.status_code == 403
