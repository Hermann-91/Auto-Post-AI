"""Portas de segurança: senha, tokens, criptografia, captcha e rate limit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.dominio.objetos_valor.enums_tenant import PapelUsuario


@dataclass(frozen=True, slots=True)
class PayloadAccessToken:
    """Identidade e tenant extraídos de um Access Token validado."""

    usuario_id: UUID
    empresa_id: UUID
    papel: PapelUsuario


class HasherSenhaPort(Protocol):
    async def gerar_hash(self, senha_plana: str) -> str: ...
    async def verificar(self, senha_plana: str, senha_hash: str) -> bool: ...
    async def verificar_dummy(self, senha_plana: str) -> None: ...


class TokenJwtPort(Protocol):
    def emitir_access_token(
        self,
        usuario_id: UUID,
        empresa_id: UUID,
        papel: PapelUsuario,
    ) -> str: ...
    def decodificar_access_token(self, token: str) -> PayloadAccessToken: ...
    def gerar_refresh_token_opaco(self) -> str: ...
    def hash_token(self, token_bruto: str) -> str: ...


class CriptografiaPort(Protocol):
    def criptografar(self, texto_plano: str) -> str: ...
    def descriptografar(self, texto_cifrado: str) -> str: ...


class CaptchaPort(Protocol):
    async def verificar(self, token_captcha: str, ip_remoto: str | None) -> bool: ...


class RateLimiterPort(Protocol):
    async def verificar_e_consumir(self, chave: str) -> tuple[bool, int]: ...
