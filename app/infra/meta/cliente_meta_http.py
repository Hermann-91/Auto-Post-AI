"""Cliente HTTP assíncrono para containers, polling e publicação na Meta Graph API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.dominio.excecoes import ErroIntegracaoMeta, ErroValidacaoDominio
from app.infra.meta.modelos_meta import (
    ErroHttpMeta,
    ErroTransitorioMeta,
    LimitePublicacaoMeta,
    StatusContainerMeta,
    extrair_erro_meta,
)

logger = logging.getLogger(__name__)
SleepFn = Callable[[float], Awaitable[None]]


class ClienteMetaHttp:
    """Cliente baixo nível para Instagram Graph API com polling e idempotência."""

    def __init__(
        self,
        graph_base_url: str = "https://graph.instagram.com",
        graph_version: str = "v22.0",
        timeout_segundos: float = 30.0,
        polling_intervalos: list[float] | None = None,
        http_client: httpx.AsyncClient | None = None,
        sleep_fn: SleepFn = asyncio.sleep,
    ) -> None:
        self._base = f"{graph_base_url.rstrip('/')}/{graph_version.strip('/')}"
        self._version = graph_version.strip("/")
        self._timeout = timeout_segundos
        self._intervalos = polling_intervalos or [3.0, 5.0, 10.0, 15.0, 15.0]
        self._http_client = http_client
        self._sleep = sleep_fn

    async def _request(
        self,
        metodo: str,
        caminho: str,
        token: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not token.strip():
            raise ErroValidacaoDominio("Access token da conta Instagram está vazio.")
        tok = token.strip()
        base_efetiva = (
            f"https://graph.facebook.com/{self._version}"
            if tok.startswith("EAA") and "graph.instagram.com" in self._base
            else self._base
        )
        url = f"{base_efetiva}/{caminho.lstrip('/')}"
        headers = {"Authorization": f"Bearer {tok}"}
        try:
            if self._http_client is not None:
                resp = await self._http_client.request(
                    metodo, url, headers=headers, params=params, json=json_body
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(
                        metodo, url, headers=headers, params=params, json=json_body
                    )
            if resp.status_code >= 400:
                detalhe = extrair_erro_meta(resp)
                logger.warning("Meta Graph API erro HTTP %s em %s", resp.status_code, caminho)
                raise ErroHttpMeta(resp.status_code, f"Meta API recusou requisição: {detalhe}")
            dados = resp.json()
            if not isinstance(dados, dict):
                raise ErroIntegracaoMeta("Resposta JSON inesperada da Meta Graph API.")
            return dados
        except ErroHttpMeta:
            raise
        except httpx.TimeoutException as exc:
            raise ErroTransitorioMeta("Timeout ao comunicar com a Meta Graph API.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ErroTransitorioMeta("Falha de transporte com a Meta Graph API.") from exc

    async def consultar_limite_publicacao(
        self,
        ig_user_id: str,
        token: str,
    ) -> LimitePublicacaoMeta:
        """Consulta cota móvel de 24h da conta Instagram antes de criar containers."""
        dados = await self._request(
            "GET",
            f"{ig_user_id}/content_publishing_limit",
            token,
            params={"fields": "quota_usage,config"},
        )
        lista = dados.get("data")
        if not isinstance(lista, list) or not lista or not isinstance(lista[0], dict):
            return LimitePublicacaoMeta(quota_usage=0, quota_total=50)
        item = lista[0]
        cfg_bruto = item.get("config")
        cfg_dict: dict[str, Any] = cfg_bruto if isinstance(cfg_bruto, dict) else {}
        uso = int(item.get("quota_usage") or 0)
        total = int(cfg_dict.get("quota_total") or 50)
        return LimitePublicacaoMeta(quota_usage=uso, quota_total=max(1, total))

    async def criar_container(
        self,
        ig_user_id: str,
        token: str,
        payload: dict[str, Any],
    ) -> str:
        """Cria container de mídia (item único, filho ou pai de carrossel)."""
        dados = await self._request("POST", f"{ig_user_id}/media", token, json_body=payload)
        container_id = str(dados.get("id") or "").strip()
        if not container_id:
            raise ErroIntegracaoMeta("Meta não retornou id do container criado.")
        return container_id

    async def consultar_status_container(
        self,
        container_id: str,
        token: str,
    ) -> StatusContainerMeta:
        """Consulta status_code atual do container na Meta."""
        dados = await self._request(
            "GET",
            container_id,
            token,
            params={"fields": "status_code,status"},
        )
        codigo = str(dados.get("status_code") or "IN_PROGRESS").strip().upper()
        detalhe = str(dados.get("status") or "").strip()
        return StatusContainerMeta(status_code=codigo, status_detalhe=detalhe)

    async def aguardar_container_pronto(
        self,
        container_id: str,
        token: str,
    ) -> StatusContainerMeta:
        """Executa polling com backoff até FINISHED/PUBLISHED ou falha definitiva."""
        for espera in self._intervalos:
            estado = await self.consultar_status_container(container_id, token)
            if estado.status_code in {"FINISHED", "PUBLISHED"}:
                return estado
            if estado.status_code in {"ERROR", "EXPIRED"}:
                raise ErroIntegracaoMeta(
                    f"Container {container_id} falhou ({estado.status_code}): "
                    f"{estado.status_detalhe or 'sem detalhe'}."
                )
            await self._sleep(espera)

        estado_final = await self.consultar_status_container(container_id, token)
        if estado_final.status_code in {"FINISHED", "PUBLISHED"}:
            return estado_final
        raise ErroIntegracaoMeta(
            f"Timeout aguardando container {container_id} "
            f"(último status: {estado_final.status_code})."
        )

    async def publicar_container(
        self,
        ig_user_id: str,
        token: str,
        creation_id: str,
    ) -> str:
        """Publica container pronto; em timeout/5xx checa antes se já consta PUBLISHED."""
        try:
            dados = await self._request(
                "POST",
                f"{ig_user_id}/media_publish",
                token,
                json_body={"creation_id": creation_id},
            )
            media_id = str(dados.get("id") or "").strip()
            if not media_id:
                raise ErroIntegracaoMeta("Meta não retornou id da mídia publicada.")
            return media_id
        except (ErroTransitorioMeta, ErroHttpMeta) as exc:
            if isinstance(exc, ErroHttpMeta) and exc.status_code < 500:
                raise
            estado = await self.consultar_status_container(creation_id, token)
            if estado.status_code == "PUBLISHED":
                return f"published:{creation_id}"
            raise ErroIntegracaoMeta(str(exc)) from exc
