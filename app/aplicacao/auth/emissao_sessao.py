"""Emissão unificada de Access Token JWT e Refresh Token opaco rotativo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.aplicacao.auth.dtos import ParTokensDTO, UsuarioAutenticadoDTO
from app.dominio.entidades.tenant import RefreshTokenRegistro, Usuario
from app.dominio.portas.repositorios_tenant import RefreshTokenRepositoryPort
from app.dominio.portas.seguranca import TokenJwtPort


class EmissorSessaoAuth:
    """Gera par de tokens e registra o estado da família de refresh token."""

    def __init__(
        self,
        tokens: TokenJwtPort,
        refresh_repo: RefreshTokenRepositoryPort,
        refresh_dias: int = 7,
    ) -> None:
        self._tokens = tokens
        self._refresh_repo = refresh_repo
        self._refresh_dias = refresh_dias

    async def emitir_sessao(
        self,
        usuario: Usuario,
        familia_id: UUID | None = None,
    ) -> tuple[ParTokensDTO, RefreshTokenRegistro]:
        """Cria Access Token JWT e novo Refresh Token persistido por hash SHA-256."""
        access_token = self._tokens.emitir_access_token(
            usuario_id=usuario.id,
            empresa_id=usuario.empresa_id,
            papel=usuario.papel,
        )
        refresh_bruto = self._tokens.gerar_refresh_token_opaco()
        refresh_hash = self._tokens.hash_token(refresh_bruto)

        registro = RefreshTokenRegistro(
            usuario_id=usuario.id,
            empresa_id=usuario.empresa_id,
            familia_id=familia_id or uuid4(),
            token_hash=refresh_hash,
            expira_em=datetime.now(UTC) + timedelta(days=self._refresh_dias),
        )
        await self._refresh_repo.salvar(registro)

        dto = ParTokensDTO(
            access_token=access_token,
            refresh_token=refresh_bruto,
            usuario=UsuarioAutenticadoDTO(
                id=usuario.id,
                empresa_id=usuario.empresa_id,
                email=usuario.email,
                papel=usuario.papel,
                ativo=usuario.ativo,
            ),
        )
        return dto, registro
