"""Testes de integração HTTP das rotas /meta/oauth/* e renovação de tokens."""

from __future__ import annotations

from uuid import UUID

from httpx import ASGITransport, AsyncClient

from app.core.config import Configuracoes
from app.main import criar_app


class _FakeAuthMetaHTTP:
    def gerar_url_autorizacao(self, state: str) -> str:
        return f"https://www.instagram.com/oauth/authorize?state={state}"

    async def trocar_codigo_por_token(self, codigo: str) -> tuple[str, int, str, str]:
        assert codigo == "cod_meta_ok"
        return "secret_long_token_real", 5184000, "178419900", "marca_dev"

    async def renovar_token_longo(self, token_atual: str) -> tuple[str, int]:
        assert token_atual == "secret_long_token_real"
        return "secret_long_token_v2", 5184000


async def test_fluxo_http_oauth_meta_e_renovacao() -> None:
    cfg = Configuracoes(
        app_env="test", argon2_time_cost=1, argon2_memory_cost_kib=8192, argon2_parallelism=1
    )
    app = criar_app(cfg)
    app.state.meta_container.auth_meta = _FakeAuthMetaHTTP()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as cli:
        reg = await cli.post(
            "/auth/register",
            json={
                "nome_empresa": "Loja OAuth",
                "email": "oauth@loja.com",
                "senha": "SenhaSuperSegura#1",
                "turnstile_token": "ok",
            },
        )
        assert reg.status_code == 201
        empresa_id = UUID(reg.json()["usuario"]["empresa_id"])

        url_resp = await cli.get("/meta/oauth/url")
        assert url_resp.status_code == 200
        state = url_resp.json()["state"]

        negado = await cli.get(f"/meta/oauth/callback?error=access_denied&state={state}")
        assert negado.status_code == 502

        cb = await cli.get(f"/meta/oauth/callback?code=cod_meta_ok&state={state}")
        assert cb.status_code == 200
        dados = cb.json()
        assert dados["username"] == "marca_dev"
        assert "access_token" not in dados
        conta_id = UUID(dados["id"])

        salva = await app.state.ia_container.conta_repo.buscar_por_id(empresa_id, conta_id)
        assert salva is not None and salva.access_token_enc != "secret_long_token_real"

        replay = await cli.get(f"/meta/oauth/callback?code=cod_meta_ok&state={state}")
        assert replay.status_code == 401

        ren = await cli.post(f"/meta/contas/{conta_id}/renovar-token")
        assert ren.status_code == 200
        salva2 = await app.state.ia_container.conta_repo.buscar_por_id(empresa_id, conta_id)
        assert salva2 is not None
        assert app.state.meta_container.cripto.descriptografar(
            salva2.access_token_enc
        ) == "secret_long_token_v2"
