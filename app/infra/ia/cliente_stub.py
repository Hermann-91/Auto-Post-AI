"""Stub fail-fast quando OPENROUTER_API_KEY não está configurada."""

from __future__ import annotations

from typing import Any

from app.dominio.excecoes import ErroValidacaoDominio


class ClienteIANaoConfigurado:
    """Falha de forma explícita quando OPENROUTER_API_KEY não foi configurada."""

    async def gerar_texto(
        self,
        system_prompt: str,
        user_prompt: str,
        modelo: str,
        formato_json: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, modelo, formato_json)
        raise ErroValidacaoDominio("OPENROUTER_API_KEY não configurada no servidor.")

    async def analisar_imagem(
        self,
        system_prompt: str,
        user_prompt: str,
        imagem_data_url: str,
        modelo: str,
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, imagem_data_url, modelo)
        raise ErroValidacaoDominio("OPENROUTER_API_KEY não configurada no servidor.")

    async def gerar_ou_editar_imagem(
        self,
        prompt: str,
        modelo: str,
        imagem_base_url: str | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        _ = (prompt, modelo, imagem_base_url)
        raise ErroValidacaoDominio("OPENROUTER_API_KEY não configurada no servidor.")

    async def gerar_embeddings(
        self,
        textos: list[str],
        modelo: str,
    ) -> tuple[list[list[float]], dict[str, Any]]:
        _ = (textos, modelo)
        raise ErroValidacaoDominio("OPENROUTER_API_KEY não configurada no servidor.")
