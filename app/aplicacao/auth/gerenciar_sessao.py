"""Casos de uso para renovação rotativa e encerramento de sessão."""

from __future__ import annotations

from app.aplicacao.auth.dtos import ParTokensDTO
from app.aplicacao.auth.emissao_sessao import EmissorSessaoAuth
from app.dominio.excecoes import ErroCredenciaisInvalidas, ErroTokenReutilizado
from app.dominio.portas.repositorios_tenant import (
    RefreshTokenRepositoryPort,
    UsuarioRepositoryPort,
)
from app.dominio.portas.seguranca import TokenJwtPort


class RenovarSessaoUseCase:
    """Rotaciona refresh token e revoga família inteira em caso de reuso."""

    def __init__(
        self,
        tokens: TokenJwtPort,
        refresh_repo: RefreshTokenRepositoryPort,
        usuario_repo: UsuarioRepositoryPort,
        emissor: EmissorSessaoAuth,
    ) -> None:
        self._tokens = tokens
        self._refresh_repo = refresh_repo
        self._usuario_repo = usuario_repo
        self._emissor = emissor

    async def executar(self, refresh_token_bruto: str | None) -> ParTokensDTO:
        """Valida refresh token atual, detecta reuso e emite novo par rotacionado."""
        if not refresh_token_bruto:
            raise ErroCredenciaisInvalidas("Refresh token ausente.")

        token_hash = self._tokens.hash_token(refresh_token_bruto)
        registro = await self._refresh_repo.buscar_por_hash(token_hash)
        if registro is None:
            raise ErroCredenciaisInvalidas("Sessão inválida ou expirada.")

        if registro.revogado or registro.substituido_por is not None:
            await self._refresh_repo.revogar_familia(registro.familia_id)
            raise ErroTokenReutilizado("Sessão encerrada por reutilização suspeita de token.")

        if not registro.esta_valido():
            raise ErroCredenciaisInvalidas("Refresh token expirado.")

        usuario = await self._usuario_repo.buscar_por_id(
            empresa_id=registro.empresa_id,
            usuario_id=registro.usuario_id,
        )
        if usuario is None or not usuario.ativo:
            await self._refresh_repo.revogar_familia(registro.familia_id)
            raise ErroCredenciaisInvalidas("Usuário inativo ou inexistente.")

        novo_par, novo_registro = await self._emissor.emitir_sessao(
            usuario=usuario,
            familia_id=registro.familia_id,
        )
        await self._refresh_repo.marcar_substituido(registro.id, novo_registro.id)
        return novo_par


class EncerrarSessaoUseCase:
    """Revoga a família de refresh tokens vinculada à sessão encerrada."""

    def __init__(
        self,
        tokens: TokenJwtPort,
        refresh_repo: RefreshTokenRepositoryPort,
    ) -> None:
        self._tokens = tokens
        self._refresh_repo = refresh_repo

    async def executar(self, refresh_token_bruto: str | None) -> None:
        """Invalida a família do token caso exista no repositório."""
        if not refresh_token_bruto:
            return
        token_hash = self._tokens.hash_token(refresh_token_bruto)
        registro = await self._refresh_repo.buscar_por_hash(token_hash)
        if registro is not None:
            await self._refresh_repo.revogar_familia(registro.familia_id)
