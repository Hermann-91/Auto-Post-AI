"""Testes de integração do painel web estático, /auth/config e CSRF global."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.core.config import Configuracoes
from app.main import criar_app


async def test_painel_estatico_config_publica_e_csp() -> None:
    cfg = Configuracoes(
        app_env="test",
        captcha_enabled=True,
        turnstile_site_key="0x4AAAAAAATestKey",
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
    )
    app = criar_app(cfg)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as cli:
        raiz = await cli.get("/", follow_redirects=False)
        assert raiz.status_code == 307 and raiz.headers["location"] == "/painel/"

        html = await cli.get("/painel/")
        assert html.status_code == 200 and "Robo-Auto-Inst" in html.text
        assert "https://challenges.cloudflare.com" in html.headers["content-security-policy"]

        js_app = await cli.get("/painel/js/app.js")
        css_main = await cli.get("/painel/css/styles.css")
        assert js_app.status_code == 200 and css_main.status_code == 200

        pub = await cli.get("/auth/config")
        assert pub.status_code == 200
        assert pub.json() == {
            "captcha_enabled": True,
            "turnstile_site_key": "0x4AAAAAAATestKey",
        }


async def test_protecao_csrf_double_submit_e_fetch_metadata() -> None:
    cfg = Configuracoes(
        app_env="test",
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
    )
    app = criar_app(cfg)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as cli:
        reg = await cli.post(
            "/auth/register",
            json={
                "nome_empresa": "Web Co",
                "email": "web@co.com",
                "senha": "SenhaSuperSegura#1",
                "turnstile_token": "ok",
            },
        )
        assert reg.status_code == 201
        csrf = cli.cookies.get("csrf_token")
        assert csrf

        # Simula navegador sem X-CSRF-Token -> 403
        sem_csrf = await cli.post(
            "/auth/refresh",
            headers={"Origin": "https://testserver", "Sec-Fetch-Site": "same-origin"},
        )
        assert sem_csrf.status_code == 403

        # Sec-Fetch-Site cross-site sem Origin -> 403
        cross = await cli.post("/auth/refresh", headers={"Sec-Fetch-Site": "cross-site"})
        assert cross.status_code == 403

        # Navegador legítimo com X-CSRF-Token pareado -> 200
        ok = await cli.post(
            "/auth/refresh",
            headers={
                "Origin": "https://testserver",
                "Sec-Fetch-Site": "same-origin",
                "X-CSRF-Token": csrf,
            },
        )
        assert ok.status_code == 200
