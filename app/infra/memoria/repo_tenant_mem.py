"""Implementação em memória dos repositórios de Empresa e Usuario."""

from __future__ import annotations

from uuid import UUID

from app.dominio.entidades.tenant import Empresa, Usuario


class InMemoryEmpresaRepository:
    """Armazena empresas em memória indexadas por UUID."""

    def __init__(self) -> None:
        self._itens: dict[UUID, Empresa] = {}

    async def salvar(self, empresa: Empresa) -> Empresa:
        self._itens[empresa.id] = empresa
        return empresa

    async def buscar_por_id(self, empresa_id: UUID) -> Empresa | None:
        return self._itens.get(empresa_id)


class InMemoryUsuarioRepository:
    """Armazena usuários em memória com índice por e-mail e filtro por tenant."""

    def __init__(self) -> None:
        self._por_id: dict[UUID, Usuario] = {}
        self._por_email: dict[str, UUID] = {}

    async def salvar(self, usuario: Usuario) -> Usuario:
        self._por_id[usuario.id] = usuario
        self._por_email[usuario.email] = usuario.id
        return usuario

    async def buscar_por_email(self, email: str) -> Usuario | None:
        uid = self._por_email.get(email.strip().lower())
        return self._por_id.get(uid) if uid else None

    async def buscar_por_id(self, empresa_id: UUID, usuario_id: UUID) -> Usuario | None:
        usuario = self._por_id.get(usuario_id)
        if usuario is None or usuario.empresa_id != empresa_id:
            return None
        return usuario
