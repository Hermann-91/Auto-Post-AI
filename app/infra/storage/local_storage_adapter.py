"""Adaptador de storage em disco local exclusivo para dev/testes."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from pathlib import Path

from app.dominio.excecoes import ErroValidacaoDominio


class LocalStorageAdapter:
    """Armazena mídias em diretório local com isolamento contra path traversal."""

    def __init__(
        self,
        base_dir: Path,
        base_url: str = "http://localhost:8000/media",
        signing_secret: str | None = None,
        presigned_ttl_segundos: int = 3600,
    ) -> None:
        self._base_dir = base_dir.resolve()
        self._base_url = base_url.rstrip("/")
        self._signing_secret = signing_secret.encode("utf-8") if signing_secret else None
        self._ttl_segundos = max(60, presigned_ttl_segundos)

    @property
    def requer_assinatura(self) -> bool:
        return self._signing_secret is not None

    def _resolver_caminho(self, chave: str) -> tuple[str, Path]:
        chave_limpa = chave.strip().lstrip("/")
        if not chave_limpa or ".." in chave_limpa.split("/"):
            raise ErroValidacaoDominio("Chave de mídia inválida para storage local.")
        destino = (self._base_dir / chave_limpa).resolve()
        if not destino.is_relative_to(self._base_dir):
            raise ErroValidacaoDominio("Caminho fora do diretório permitido de storage.")
        return chave_limpa, destino

    def _assinar(self, chave_limpa: str, exp: int) -> str:
        assert self._signing_secret is not None
        msg = f"{chave_limpa}:{exp}".encode()
        return hmac.new(self._signing_secret, msg, hashlib.sha256).hexdigest()

    def _montar_url_publica(self, chave_limpa: str) -> str:
        if self._signing_secret is None:
            return f"{self._base_url}/{chave_limpa}"
        exp = int(time.time()) + self._ttl_segundos
        sig = self._assinar(chave_limpa, exp)
        return f"{self._base_url}/{chave_limpa}?exp={exp}&sig={sig}"

    def validar_assinatura(self, chave: str, exp: int | None, sig: str | None) -> Path:
        """Valida expiração e HMAC da URL local antes de expor arquivo à Meta."""
        chave_limpa, destino = self._resolver_caminho(chave)
        if self._signing_secret is not None:
            if exp is None or not sig or exp < int(time.time()):
                raise ErroValidacaoDominio("Assinatura de mídia ausente ou expirada.")
            esperado = self._assinar(chave_limpa, exp)
            if not hmac.compare_digest(esperado, sig.strip()):
                raise ErroValidacaoDominio("Assinatura de mídia inválida.")
        return destino

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
        return self._montar_url_publica(chave_limpa)

    async def baixar_bytes(self, chave: str) -> bytes:
        _, destino = self._resolver_caminho(chave)
        if not destino.exists():
            raise ErroValidacaoDominio("Arquivo de mídia não encontrado no storage local.")
        return await asyncio.to_thread(destino.read_bytes)

    async def obter_url_publica(self, chave: str) -> str:
        chave_limpa, _ = self._resolver_caminho(chave)
        return self._montar_url_publica(chave_limpa)

    async def remover_objeto(self, chave: str) -> None:
        _, destino = self._resolver_caminho(chave)
        await asyncio.to_thread(destino.unlink, True)
