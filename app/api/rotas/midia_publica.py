"""Endpoint público assinado para entrega de mídia local da VPS à Meta Graph API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.dependencias.container_ia import ContainerIA
from app.api.dependencias.provedores_ia import obter_container_ia
from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.storage.local_storage_adapter import LocalStorageAdapter

router = APIRouter(tags=["midia-publica"])

_MIME_SEGURO: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}


@router.get("/media/{chave:path}", include_in_schema=False)
async def servir_midia_local_assinada(
    chave: str,
    ia: Annotated[ContainerIA, Depends(obter_container_ia)],
    exp: Annotated[int | None, Query()] = None,
    sig: Annotated[str | None, Query()] = None,
) -> FileResponse:
    """Entrega mídia do disco da VPS validando assinatura HMAC e extensão segura."""
    if not isinstance(ia.storage, LocalStorageAdapter):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Indisponível.")
    try:
        destino = ia.storage.validar_assinatura(chave, exp, sig)
    except ErroValidacaoDominio as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    media_type = _MIME_SEGURO.get(destino.suffix.lower())
    if media_type is None or not destino.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo de mídia não encontrado.",
        )
    return FileResponse(
        path=destino,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
