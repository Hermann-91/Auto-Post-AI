"""Adaptador de storage em disco local exclusivo para dev/testes."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.dominio.excecoes import ErroValidacaoDominio


class LocalStorageAdapter:
    """Armazena mídias em diretório local com isolamento contra path traversal."""

    def __init__(self, base_dir: Path, base_url: str = "http://localhost:8000/media") -> None:
        self._base_dir = base_dir.resolve()
        self._base_url = base_url.rstrip("/")

    def _resolver_caminho(self, chave: str) -> tuple[str, Path]:
        chave_limpa = chave.strip().lstrip("/")
        if not chave_limpa or ".." in chave_limpa.split("/"):
            raise ErroValidacaoDominio("Chave de mídia inválida para storage local.")
        destino = (self._base_dir / chave_limpa).resolve()
        if not destino.is_relative_to(self._base_dir):
            raise ErroValidacaoDominio("Caminho fora do diretório permitido de storage.")
        return chave_limpa, destino

    @staticmethod
    def _gravar_sync(destino: Path, conteudo: bytes) -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)

    async def enviar_bytes(self, chave: str, conteudo: bytes, content_type: str) -> str:
        if not conteudo:
            raise ErroValidacaoDominio("Conteúdo do arquivo não pode ser vazio.")
        _ = content_type
        chave_limpa, destino = self._resolver_caminho(chave)
        await asyncio.to_thread(self._gravar_sync, destino, conteudo)
        return f"{self._base_url}/{chave_limpa}"

    async def obter_url_publica(self, chave: str) -> str:
        chave_limpa, _ = self._resolver_caminho(chave)
        return f"{self._base_url}/{chave_limpa}"

    async def remover_objeto(self, chave: str) -> None:
        _, destino = self._resolver_caminho(chave)
        await asyncio.to_thread(destino.unlink, True)
