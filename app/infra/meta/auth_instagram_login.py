"""Adaptador OAuth oficial: Instagram API with Instagram Login (graph.instagram.com)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.dominio.excecoes import ErroIntegracaoMeta, ErroValidacaoDominio

logger = logging.getLogger(__name__)
_SCOPES_IG = "instagram_business_basic,instagram_business_content_publish"
_EXPIRACAO_PADRAO_LONGO_SEG = 60 * 86400


class AuthMetaNaoConfigurado:
    """Stub fail-fast quando credenciais OAuth Meta não estão configuradas."""

    def gerar_url_autorizacao(self, state: str) -> str:
        _ = state
        raise ErroValidacaoDominio("Credenciais OAuth da Meta não configuradas no servidor.")

    async def trocar_codigo_por_token(self, codigo: str) -> tuple[str, int, str, str]:
        _ = codigo
        raise ErroValidacaoDominio("Credenciais OAuth da Meta não configuradas no servidor.")

    async def renovar_token_longo(self, token_atual: str) -> tuple[str, int]:
        _ = token_atual
        raise ErroValidacaoDominio("Credenciais OAuth da Meta não configuradas no servidor.")


class AuthInstagramLoginAdapter:
    """Autenticação OAuth V1 via Instagram Login (sem exigência de Página Facebook)."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        redirect_uri: str,
        authorize_url: str = "https://www.instagram.com/oauth/authorize",
        token_url: str = "https://api.instagram.com/oauth/access_token",
        graph_base_url: str = "https://graph.instagram.com",
        graph_version: str = "v22.0",
        timeout_segundos: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not app_id.strip() or not app_secret.strip() or not redirect_uri.strip():
            raise ErroValidacaoDominio(
                "META_APP_ID, META_APP_SECRET e META_REDIRECT_URI são obrigatórios."
            )
        self._app_id = app_id.strip()
        self._app_secret = app_secret.strip()
        self._redirect_uri = redirect_uri.strip()
        self._authorize_url = authorize_url.rstrip("/")
        self._token_url = token_url.rstrip("/")
        self._graph_base_url = graph_base_url.rstrip("/")
        self._graph_version = graph_version.strip("/")
        self._timeout = timeout_segundos
        self._http_client = http_client

    def gerar_url_autorizacao(self, state: str) -> str:
        """Gera URL de consentimento OAuth da Meta com state anti-CSRF."""
        state_limpo = state.strip()
        if not state_limpo:
            raise ErroValidacaoDominio("Parâmetro state OAuth não pode ser vazio.")
        params = urlencode(
            {
                "enable_fb_login": "0",
                "force_authentication": "1",
                "client_id": self._app_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": _SCOPES_IG,
                "state": state_limpo,
            }
        )
        return f"{self._authorize_url}?{params}"

    async def _enviar(
        self,
        metodo: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            if self._http_client is not None:
                resp = await self._http_client.request(
                    metodo, url, params=params, data=data, headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(
                        metodo, url, params=params, data=data, headers=headers
                    )
            resp.raise_for_status()
            corpo = resp.json()
            if not isinstance(corpo, dict):
                raise ErroIntegracaoMeta("Resposta JSON inválida no OAuth Meta.")
            return corpo
        except httpx.HTTPStatusError as exc:
            codigo = exc.response.status_code
            logger.warning("OAuth Meta retornou HTTP %s", codigo)
            raise ErroIntegracaoMeta(f"Falha OAuth Meta (HTTP {codigo}).") from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Erro de rede no OAuth Meta: %s", type(exc).__name__)
            raise ErroIntegracaoMeta("Falha de comunicação com OAuth da Meta.") from exc

    @staticmethod
    def _extrair_curto(dados: dict[str, Any]) -> tuple[str, str]:
        raiz: dict[str, Any] = dados
        lista = dados.get("data")
        if isinstance(lista, list) and lista and isinstance(lista[0], dict):
            raiz = lista[0]
        token = str(raiz.get("access_token") or "").strip()
        user_id = str(raiz.get("user_id") or "").strip()
        if not token:
            raise ErroIntegracaoMeta("Meta não retornou short-lived access_token.")
        return token, user_id

    async def trocar_codigo_por_token(self, codigo: str) -> tuple[str, int, str, str]:
        """Troca code por Long-Lived Token (60 dias) e resolve ig_user_id + username."""
        codigo_limpo = codigo.split("#", 1)[0].strip()
        if not codigo_limpo:
            raise ErroValidacaoDominio("Código de autorização Meta inválido.")

        curto_resp = await self._enviar(
            "POST",
            self._token_url,
            data={
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri,
                "code": codigo_limpo,
            },
        )
        short_token, fallback_user_id = self._extrair_curto(curto_resp)

        longo_resp = await self._enviar(
            "GET",
            f"{self._graph_base_url}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": self._app_secret,
                "access_token": short_token,
            },
        )
        long_token = str(longo_resp.get("access_token") or "").strip()
        if not long_token:
            raise ErroIntegracaoMeta("Meta não retornou long-lived access_token.")
        expires_in = int(longo_resp.get("expires_in") or _EXPIRACAO_PADRAO_LONGO_SEG)

        perfil = await self._enviar(
            "GET",
            f"{self._graph_base_url}/{self._graph_version}/me",
            params={"fields": "user_id,username"},
            headers={"Authorization": f"Bearer {long_token}"},
        )
        ig_user_id = str(perfil.get("user_id") or perfil.get("id") or fallback_user_id).strip()
        username = str(perfil.get("username") or "").strip().lstrip("@")
        if not ig_user_id or not username:
            raise ErroIntegracaoMeta("Meta não retornou user_id e username da conta IG.")
        return long_token, max(60, expires_in), ig_user_id, username

    async def renovar_token_longo(self, token_atual: str) -> tuple[str, int]:
        """Renova um Long-Lived Token ativo antes do prazo de expiração."""
        limpo = token_atual.strip()
        if not limpo:
            raise ErroValidacaoDominio("Token atual inválido para renovação Meta.")
        resp = await self._enviar(
            "GET",
            f"{self._graph_base_url}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": limpo},
        )
        novo_token = str(resp.get("access_token") or "").strip()
        if not novo_token:
            raise ErroIntegracaoMeta("Meta não retornou novo token na renovação.")
        expires_in = int(resp.get("expires_in") or _EXPIRACAO_PADRAO_LONGO_SEG)
        return novo_token, max(60, expires_in)
