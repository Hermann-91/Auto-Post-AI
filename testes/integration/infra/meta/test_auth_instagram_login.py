"""Testes de integração do adaptador OAuth Instagram Login via MockTransport."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.dominio.excecoes import ErroIntegracaoMeta, ErroValidacaoDominio
from app.infra.meta import AuthInstagramLoginAdapter, AuthMetaNaoConfigurado


async def test_oauth_instagram_login_troca_e_renovacao() -> None:
    chamadas: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append((request.method, request.url.path))
        if request.url.path == "/oauth/access_token":
            corpo = request.content.decode("utf-8")
            assert "code=cod_abc" in corpo
            return httpx.Response(200, json={"access_token": "short_tok", "user_id": 111})
        if request.url.path == "/access_token":
            assert request.url.params["grant_type"] == "ig_exchange_token"
            return httpx.Response(
                200,
                json={"access_token": "long_tok", "token_type": "bearer", "expires_in": 5184000},
            )
        if request.url.path == "/v22.0/me":
            assert request.headers["authorization"] == "Bearer long_tok"
            return httpx.Response(200, json={"user_id": "17841999", "username": "dev_insta"})
        if request.url.path == "/refresh_access_token":
            assert request.url.params["grant_type"] == "ig_refresh_token"
            return httpx.Response(200, json={"access_token": "long_tok_v2", "expires_in": 5184000})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cli:
        adapter = AuthInstagramLoginAdapter(
            app_id="app_123",
            app_secret="segredo_meta",
            redirect_uri="https://app.teste.com/meta/oauth/callback",
            http_client=cli,
        )
        url = adapter.gerar_url_autorizacao("state_xyz")
        qs = parse_qs(urlparse(url).query)
        assert qs["client_id"] == ["app_123"]
        assert qs["scope"] == ["instagram_business_basic,instagram_business_content_publish"]
        assert qs["state"] == ["state_xyz"]

        tok, exp, uid, uname = await adapter.trocar_codigo_por_token("cod_abc#_")
        assert (tok, exp, uid, uname) == ("long_tok", 5184000, "17841999", "dev_insta")

        novo_tok, novo_exp = await adapter.renovar_token_longo(tok)
        assert (novo_tok, novo_exp) == ("long_tok_v2", 5184000)

    assert len(chamadas) == 4


async def test_oauth_erro_http_e_stub_nao_configurado() -> None:
    def handler_erro(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Invalid code"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_erro)) as cli:
        adapter = AuthInstagramLoginAdapter(
            app_id="app_1",
            app_secret="sec_super_secreto",
            redirect_uri="https://app.teste.com/cb",
            http_client=cli,
        )
        with pytest.raises(ErroIntegracaoMeta) as exc_info:
            await adapter.trocar_codigo_por_token("invalido")
        assert "sec_super_secreto" not in str(exc_info.value)

    stub = AuthMetaNaoConfigurado()
    with pytest.raises(ErroValidacaoDominio):
        stub.gerar_url_autorizacao("s")
    with pytest.raises(ErroValidacaoDominio):
        await stub.trocar_codigo_por_token("c")
    with pytest.raises(ErroValidacaoDominio):
        await stub.renovar_token_longo("t")
