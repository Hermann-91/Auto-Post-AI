"""DTOs imutáveis de entrada e saída dos casos de uso de autenticação."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.dominio.objetos_valor.enums_tenant import PapelUsuario


@dataclass(frozen=True, slots=True)
class RegistroUsuarioCmd:
    """Comando para cadastrar nova empresa e seu primeiro usuário administrador."""

    nome_empresa: str
    email: str
    senha: str
    token_captcha: str
    ip_remoto: str | None


@dataclass(frozen=True, slots=True)
class LoginCmd:
    """Comando de autenticação com e-mail, senha e token Turnstile."""

    email: str
    senha: str
    token_captcha: str
    ip_remoto: str | None


@dataclass(frozen=True, slots=True)
class UsuarioAutenticadoDTO:
    """Visão segura do usuário autenticado sem expor senha_hash."""

    id: UUID
    empresa_id: UUID
    email: str
    papel: PapelUsuario
    ativo: bool


@dataclass(frozen=True, slots=True)
class ParTokensDTO:
    """Par de credenciais emitidas após registro, login ou renovação."""

    access_token: str
    refresh_token: str
    usuario: UsuarioAutenticadoDTO
