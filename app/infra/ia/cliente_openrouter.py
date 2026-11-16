"""Adaptador HTTP assíncrono para OpenRouter (texto, visão e Nano Banana)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import httpx

from app.dominio.excecoes import ErroIntegracaoIA, ErroValidacaoDominio
from app.infra.ia.cliente_stub import ClienteIANaoConfigurado
from app.infra.ia.openrouter_parser import (
    decodificar_data_uri,
    extrair_embeddings,
    extrair_mensagem,
    extrair_texto_mensagem,
    extrair_url_imagem_gerada,
    extrair_usage,
    modelo_eh_gratuito,
    montar_payload_embeddings,
    montar_payload_imagem,
    montar_payload_texto,
    montar_payload_visao,
    validar_url_imagem,
)

logger = logging.getLogger(__name__)
_MAX_IMAGEM_BYTES = 20 * 1024 * 1024
_STATUS_FALLBACK = {429, 500, 502, 503, 504}

__all__ = ["ClienteIANaoConfigurado", "ClienteOpenRouter"]


class _ErroHttpOpenRouter(ErroIntegracaoIA):
    def __init__(self, status_code: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status_code = status_code


class ClienteOpenRouter:
    """Cliente OpenRouter compatível com DeepSeek, Visão Flash e Nano Banana."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_segundos: float = 60.0,
        site_url: str | None = None,
        app_title: str = "Robo-Auto-Inst",
        modelo_fallback_free: str = "openrouter/free",
        fallback_automatico: bool = True,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ErroValidacaoDominio("OPENROUTER_API_KEY não pode ser vazia.")
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_segundos
        self._site_url = site_url
        self._app_title = app_title
        self._modelo_fallback_free = modelo_fallback_free
        self._fallback_automatico = fallback_automatico
        self._http_client = http_client

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json", "X-Title": self._app_title,
        }
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        return headers

    async def _enviar_http(
        self, metodo: str, url: str,
        headers: dict[str, str] | None = None, payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.request(metodo, url, headers=headers, json=payload)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.request(metodo, url, headers=headers, json=payload)

    async def _requisitar(
        self, metodo: str, caminho: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self._base_url}{caminho}"
        try:
            resp = await self._enviar_http(metodo, url, headers=self._headers(), payload=payload)
            resp.raise_for_status()
            dados = resp.json()
            if not isinstance(dados, dict):
                raise ErroIntegracaoIA("Resposta JSON inesperada do OpenRouter.")
            return dados
        except httpx.HTTPStatusError as exc:
            codigo = exc.response.status_code
            logger.warning("OpenRouter retornou HTTP %s em %s", codigo, caminho)
            raise _ErroHttpOpenRouter(codigo, f"OpenRouter falhou (HTTP {codigo}).") from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Falha de comunicação com OpenRouter: %s", type(exc).__name__)
            raise ErroIntegracaoIA("Falha de rede ao consultar OpenRouter.") from exc

    async def _baixar_imagem_https(self, url: str) -> bytes:
        validar_url_imagem(url)
        try:
            resp = await self._enviar_http("GET", url)
            resp.raise_for_status()
            dados = resp.content
        except httpx.HTTPError as exc:
            raise ErroIntegracaoIA("Falha ao baixar imagem gerada pelo OpenRouter.") from exc
        if not dados or len(dados) > _MAX_IMAGEM_BYTES:
            raise ErroIntegracaoIA("Imagem baixada vazia ou acima do limite permitido.")
        return dados

    async def _chat_com_fallback(
        self, payload: dict[str, Any], modelo: str, permitir_fallback_free: bool
    ) -> dict[str, Any]:
        try:
            return await self._requisitar("POST", "/chat/completions", payload)
        except _ErroHttpOpenRouter as exc:
            pode_fallback = (
                permitir_fallback_free
                and self._fallback_automatico
                and exc.status_code in _STATUS_FALLBACK
                and not modelo_eh_gratuito(modelo)
            )
            if not pode_fallback:
                raise ErroIntegracaoIA(str(exc)) from exc
            payload_fb = {**payload, "model": self._modelo_fallback_free}
            try:
                return await self._requisitar("POST", "/chat/completions", payload_fb)
            except _ErroHttpOpenRouter as exc_fb:
                raise ErroIntegracaoIA(str(exc_fb)) from exc_fb

    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        """Gera texto ou JSON estruturado no OpenRouter com extração de usage.cost."""
        payload = montar_payload_texto(system_prompt, user_prompt, modelo, formato_json)
        dados = await self._chat_com_fallback(payload, modelo, permitir_fallback_free=True)
        texto = extrair_texto_mensagem(extrair_mensagem(dados))
        return texto, extrair_usage(dados, modelo)

    async def analisar_imagem(
        self, system_prompt: str, user_prompt: str, imagem_data_url: str, modelo: str
    ) -> tuple[str, dict[str, Any]]:
        """Executa curadoria visual multimodal com miniatura já compactada."""
        payload = montar_payload_visao(system_prompt, user_prompt, imagem_data_url, modelo)
        dados = await self._chat_com_fallback(payload, modelo, permitir_fallback_free=True)
        texto = extrair_texto_mensagem(extrair_mensagem(dados))
        return texto, extrair_usage(dados, modelo)

    async def _executar_payload_imagem(
        self, payload: dict[str, Any], modelo: str
    ) -> tuple[bytes, dict[str, Any]]:
        dados = await self._chat_com_fallback(payload, modelo, permitir_fallback_free=False)
        url_saida = extrair_url_imagem_gerada(extrair_mensagem(dados))
        img_bytes = (
            decodificar_data_uri(url_saida)
            if url_saida.startswith("data:image/")
            else await self._baixar_imagem_https(url_saida)
        )
        return img_bytes, extrair_usage(dados, modelo)

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        """Gera ou edita imagem via Nano Banana (modalities=['image', 'text'])."""
        return await self._executar_payload_imagem(
            montar_payload_imagem(prompt, modelo, imagem_base_url), modelo
        )

    async def gerar_imagem_com_referencias(
        self, prompt: str, modelo: str, imagens_base_urls: Sequence[str]
    ) -> tuple[bytes, dict[str, Any]]:
        """Gera ou edita imagem enviando múltiplas referências visuais ao Nano Banana."""
        return await self._executar_payload_imagem(
            montar_payload_imagem(prompt, modelo, imagens_referencia_urls=imagens_base_urls),
            modelo,
        )

    async def gerar_embeddings(
        self, textos: list[str], modelo: str
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """Gera embeddings em lote no OpenRouter /embeddings com usage.cost."""
        if not textos:
            return [], extrair_usage({}, modelo)
        payload = montar_payload_embeddings(textos, modelo)
        dados = await self._requisitar("POST", "/embeddings", payload)
        return extrair_embeddings(dados, len(textos)), extrair_usage(dados, modelo)

    async def consultar_geracao(self, gen_id: str) -> dict[str, Any]:
        """Audita custo total, provedor e tokens em cache de uma geração OpenRouter."""
        if not gen_id.strip():
            raise ErroValidacaoDominio("gen_id é obrigatório para auditoria OpenRouter.")
        dados = await self._requisitar("GET", f"/generation?id={gen_id.strip()}")
        interno = dados.get("data")
        return dict(interno) if isinstance(interno, dict) else dados
