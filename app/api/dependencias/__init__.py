"""Dependências FastAPI: container de autenticação e contexto multi-tenant."""

from app.api.dependencias.container_auth import (
    ContainerAuth,
    construir_container_auth,
    obter_autenticar_uc,
    obter_config_app,
    obter_container_auth,
    obter_encerrar_uc,
    obter_registrar_uc,
    obter_renovar_uc,
)
from app.api.dependencias.usuario_atual import (
    exigir_papel_admin,
    obter_usuario_atual,
)

__all__ = [
    "ContainerAuth",
    "construir_container_auth",
    "exigir_papel_admin",
    "obter_autenticar_uc",
    "obter_config_app",
    "obter_container_auth",
    "obter_encerrar_uc",
    "obter_registrar_uc",
    "obter_renovar_uc",
    "obter_usuario_atual",
]
