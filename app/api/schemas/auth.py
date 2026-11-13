"""Schemas Pydantic para registro, login, sessão e perfil do usuário."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.dominio.objetos_valor.enums_tenant import PapelUsuario


class RegistroRequest(BaseModel):
    """Payload público para cadastro de nova empresa e administrador."""

    model_config = ConfigDict(extra="forbid")

    nome_empresa: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)
    turnstile_token: str = Field(default="")


class LoginRequest(BaseModel):
    """Payload público de autenticação."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)
    turnstile_token: str = Field(default="")


class UsuarioResponse(BaseModel):
    """Representação segura do usuário autenticado (sem senha_hash)."""

    id: UUID
    empresa_id: UUID
    email: EmailStr
    papel: PapelUsuario
    ativo: bool


class SessaoResponse(BaseModel):
    """Resposta padrão para operações que emitem cookies de sessão."""

    mensagem: str
    usuario: UsuarioResponse


class MensagemResponse(BaseModel):
    """Resposta simples com mensagem informativa."""

    mensagem: str
