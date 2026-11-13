"""Endpoints de saúde e prontidão para Docker e proxy reverso."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.dependencias.container_auth import (
    ContainerAuth,
    obter_config_app,
    obter_container_auth,
)
from app.core.config import Configuracoes
from app.infra.db.sessao import verificar_saude_banco

router = APIRouter(tags=["saude"])


@router.get("/healthz")
async def healthcheck(
    config: Annotated[Configuracoes, Depends(obter_config_app)],
) -> dict[str, str]:
    """Confirma que o processo ASGI da API está ativo."""
    return {"status": "ok", "env": config.app_env}


@router.get("/readyz")
async def readiness(
    container: Annotated[ContainerAuth, Depends(obter_container_auth)],
) -> JSONResponse:
    """Confirma prontidão da API, banco SQL e Redis para receber tráfego."""
    try:
        if container.db_engine is not None:
            await verificar_saude_banco(container.db_engine)
        if container.redis_client is not None:
            await container.redis_client.ping()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unready"},
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready"})
