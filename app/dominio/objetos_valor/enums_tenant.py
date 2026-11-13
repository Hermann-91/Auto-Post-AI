"""Enumerações ligadas a empresa, usuários e contas Instagram."""

from __future__ import annotations

from enum import StrEnum


class PapelUsuario(StrEnum):
    """Níveis de permissão dentro de um mesmo tenant (empresa)."""

    ADMIN = "ADMIN"
    EDITOR = "EDITOR"


class PlanoEmpresa(StrEnum):
    """Planos comerciais que parametrizam cotas e limites padrão."""

    TRIAL = "TRIAL"
    BASICO = "BASICO"
    PRO = "PRO"
    AGENCIA = "AGENCIA"


class ProvedorMeta(StrEnum):
    """Fluxos suportados para autenticação na Meta Graph API."""

    INSTAGRAM_LOGIN = "instagram_login"
    FACEBOOK_LOGIN = "facebook_login"
