"""Serviço de emissão/validação de JWT e tokens opacos de refresh."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError

from app.dominio.excecoes import ErroCredenciaisInvalidas
from app.dominio.objetos_valor.enums_tenant import PapelUsuario
from app.dominio.portas.seguranca import PayloadAccessToken


class JwtTokenService:
    """Implementa criação e validação estrita de tokens JWT multi-tenant."""

    def __init__(
        self,
        chave_secreta: str,
        algoritmo: str = "HS256",
        issuer: str = "robo-auto-inst",
        audience: str = "robo-auto-inst-api",
        access_minutos: int = 15,
    ) -> None:
        self._chave_secreta = chave_secreta
        self._algoritmo = algoritmo
        self._issuer = issuer
        self._audience = audience
        self._access_minutos = access_minutos

    def emitir_access_token(
        self,
        usuario_id: UUID,
        empresa_id: UUID,
        papel: PapelUsuario,
    ) -> str:
        """Assina Access Token curto contendo identidade e tenant do usuário."""
        agora = datetime.now(UTC)
        expira = agora + timedelta(minutes=self._access_minutos)
        claims: dict[str, Any] = {
            "sub": str(usuario_id),
            "empresa_id": str(empresa_id),
            "papel": papel.value,
            "type": "access",
            "jti": str(uuid4()),
            "iss": self._issuer,
            "aud": self._audience,
            "iat": int(agora.timestamp()),
            "exp": int(expira.timestamp()),
        }
        return jwt.encode(claims, self._chave_secreta, algorithm=self._algoritmo)

    def decodificar_access_token(self, token: str) -> PayloadAccessToken:
        """Valida assinatura, audiência, emissor, expiração e tipo do token."""
        try:
            dados = jwt.decode(
                token,
                self._chave_secreta,
                algorithms=[self._algoritmo],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["sub", "empresa_id", "papel", "type", "exp", "iss", "aud"]},
            )
            if dados.get("type") != "access":
                raise ErroCredenciaisInvalidas("Token inválido.")
            return PayloadAccessToken(
                usuario_id=UUID(str(dados["sub"])),
                empresa_id=UUID(str(dados["empresa_id"])),
                papel=PapelUsuario(str(dados["papel"])),
            )
        except (InvalidTokenError, KeyError, ValueError) as exc:
            raise ErroCredenciaisInvalidas("Sessão inválida ou expirada.") from exc

    def gerar_refresh_token_opaco(self) -> str:
        """Gera segredo aleatório de alta entropia para cookie de refresh."""
        return secrets.token_urlsafe(48)

    def hash_token(self, token_bruto: str) -> str:
        """Calcula hash SHA-256 determinístico para persistência segura do refresh token."""
        return hashlib.sha256(token_bruto.encode("utf-8")).hexdigest()
