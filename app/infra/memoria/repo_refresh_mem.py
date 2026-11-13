"""Implementação em memória para estado e rotação de Refresh Tokens."""

from __future__ import annotations

from uuid import UUID

from app.dominio.entidades.tenant import RefreshTokenRegistro


class InMemoryRefreshTokenRepository:
    """Mantém refresh tokens por hash SHA-256 e revoga famílias comprometidas."""

    def __init__(self) -> None:
        self._por_id: dict[UUID, RefreshTokenRegistro] = {}
        self._por_hash: dict[str, UUID] = {}

    async def salvar(self, registro: RefreshTokenRegistro) -> RefreshTokenRegistro:
        self._por_id[registro.id] = registro
        self._por_hash[registro.token_hash] = registro.id
        return registro

    async def buscar_por_hash(self, token_hash: str) -> RefreshTokenRegistro | None:
        tid = self._por_hash.get(token_hash)
        return self._por_id.get(tid) if tid else None

    async def marcar_substituido(self, token_id: UUID, novo_id: UUID) -> None:
        registro = self._por_id.get(token_id)
        if registro is not None:
            registro.substituido_por = novo_id

    async def revogar_familia(self, familia_id: UUID) -> None:
        for registro in self._por_id.values():
            if registro.familia_id == familia_id:
                registro.revogado = True
