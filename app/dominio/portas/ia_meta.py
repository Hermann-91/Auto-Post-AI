"""Portas de IA (OpenRouter), tendências web e integração oficial Meta."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.objetos_valor.enums_conteudo import TipoMidia


class ClienteIAPort(Protocol):
    async def gerar_texto(
        self,
        system_prompt: str,
        user_prompt: str,
        modelo: str,
        formato_json: bool = False,
    ) -> tuple[str, dict[str, Any]]: ...
    async def gerar_ou_editar_imagem(
        self,
        prompt: str,
        modelo: str,
        imagem_base_url: str | None = None,
    ) -> tuple[bytes, dict[str, Any]]: ...


class ClienteVisaoPort(Protocol):
    async def analisar_imagem(
        self,
        system_prompt: str,
        user_prompt: str,
        imagem_data_url: str,
        modelo: str,
    ) -> tuple[str, dict[str, Any]]: ...


class PesquisaTendenciasPort(Protocol):
    async def buscar_tendencias(
        self,
        nicho: str,
        regiao: str,
        ttl_horas: int = 48,
    ) -> dict[str, Any]: ...


class ProvedorAuthMetaPort(Protocol):
    def gerar_url_autorizacao(self, state: str) -> str: ...
    async def trocar_codigo_por_token(self, codigo: str) -> tuple[str, int, str, str]: ...
    async def renovar_token_longo(self, token_atual: str) -> tuple[str, int]: ...


class PublicadorMidiaStrategyPort(Protocol):
    tipo_suportado: TipoMidia

    async def publicar(
        self,
        conta: ContaInstagram,
        token_descriptografado: str,
        postagem: Postagem,
        urls_publicas: list[str],
    ) -> tuple[str, str]: ...


class OrcamentoCheckerPort(Protocol):
    async def verificar_disponibilidade(
        self,
        empresa_id: UUID,
        custo_previsto: Decimal,
    ) -> bool: ...
