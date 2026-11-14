"""Testes de integração do painel web estático, /auth/config e CSRF global."""

from __future__ import annotations

from uuid import UUID

from httpx import ASGITransport, AsyncClient

from app.core.config import Configuracoes
from app.dominio.entidades.publicacao import Postagem
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem, TipoMidia
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
        assert "sec-conta-meta" in html.text and "Meta for Developers" in html.text
        assert "https://challenges.cloudflare.com" in html.headers["content-security-policy"]

        js_app = await cli.get("/painel/js/app.js")
        js_cfg = await cli.get("/painel/js/config_custos.js")
        css_main = await cli.get("/painel/css/styles.css")
        assert js_app.status_code == 200 and css_main.status_code == 200 and "_blank" in js_cfg.text

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


async def test_cadastro_manual_conta_instagram_fernet_e_repost() -> None:
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
                "nome_empresa": "SaaS IG Co",
                "email": "admin@saasig.com",
                "senha": "SenhaSuperSegura#1",
                "turnstile_token": "ok",
            },
        )
        assert reg.status_code == 201
        empresa_id = UUID(reg.json()["usuario"]["empresa_id"])
        csrf = cli.cookies.get("csrf_token") or ""
        headers = {"Origin": "https://testserver", "X-CSRF-Token": csrf}

        manual = await cli.post(
            "/contas",
            headers=headers,
            json={
                "username": "@marca_oficial",
                "ig_user_id": "17841400999",
                "access_token": "IGQWR_TOKEN_SECRETO_META",
            },
        )
        assert manual.status_code == 201
        conta_id = UUID(manual.json()["id"])

        conta_db = await app.state.ia_container.conta_repo.buscar_por_id(empresa_id, conta_id)
        assert conta_db is not None
        assert conta_db.access_token_enc != "IGQWR_TOKEN_SECRETO_META"
        token_dec = app.state.meta_container.cripto.descriptografar(conta_db.access_token_enc)
        assert token_dec == "IGQWR_TOKEN_SECRETO_META"

        editada = await cli.post(
            "/contas",
            headers=headers,
            json={
                "conta_id": str(conta_id),
                "username": "@marca_renomeada",
                "ig_user_id": "17841400999",
                "access_token": "",
            },
        )
        assert editada.status_code == 201
        assert editada.json()["username"] == "marca_renomeada"

        post_pub = await app.state.ia_container.post_repo.salvar(
            Postagem(
                empresa_id=empresa_id,
                conta_ig_id=conta_id,
                tipo_midia=TipoMidia.IMAGE,
                midias_chaves=[f"{empresa_id}/{conta_id}/IA-Cria/arte.jpg"],
                legenda="Post já publicado que será repostado",
                status=StatusPostagem.PUBLICADO,
                meta_media_id="179000001",
            )
        )
        reagendado = await cli.post(
            f"/posts/{conta_id}/{post_pub.id}/agendar",
            headers=headers,
            json={"agendado_para": "2027-01-15T18:00:00Z"},
        )
        assert reagendado.status_code == 200 and reagendado.json()["status"] == "AGENDADO"

        lista = await cli.get("/contas")
        assert lista.status_code == 200 and len(lista.json()) == 1
