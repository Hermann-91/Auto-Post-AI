"""Portas de armazenamento de mídia em nuvem, pipeline determinístico e Drive."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.dominio.objetos_valor.enums_conteudo import TipoMidia


class StorageMidiaPort(Protocol):
    async def enviar_bytes(self, chave: str, conteudo: bytes, content_type: str) -> str: ...
    async def obter_url_publica(self, chave: str) -> str: ...
    async def remover_objeto(self, chave: str) -> None: ...


class MidiaStrategyPort(Protocol):
    tipo_suportado: TipoMidia

    async def processar(
        self,
        arquivos_bytes: list[bytes],
        parametros: dict[str, Any],
    ) -> list[bytes]: ...


class DriveImportPort(Protocol):
    async def listar_imagens(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        pasta_drive_id: str | None = None,
    ) -> list[dict[str, str]]: ...
    async def baixar_arquivo(self, empresa_id: UUID, conta_ig_id: UUID, file_id: str) -> bytes: ...
