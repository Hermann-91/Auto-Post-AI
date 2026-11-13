"""Endpoints de saúde e prontidão para Docker e proxy reverso."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencias.container_auth import obter_config_app
from app.core.config import Configuracoes

router = APIRouter(tags=["saude"])


@router.get("/healthz")
async def healthcheck(
    config: Annotated[Configuracoes, Depends(obter_config_app)],
) -> dict[str, str]:
    """Confirma que o processo ASGI da API está ativo."""
    return {"status": "ok", "env": config.app_env}


@router.get("/readyz")
async def readiness() -> dict[str, str]:
    """Confirma prontidão da aplicação para receber tráfego."""
    return {"status": "ready"}
