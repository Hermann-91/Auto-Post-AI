"""Adaptadores de armazenamento de mídia em nuvem (R2/S3) e local (dev/test)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Configuracoes
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.infra.storage.local_storage_adapter import LocalStorageAdapter
from app.infra.storage.s3_r2_adapter import S3R2StorageAdapter, criar_cliente_s3

__all__ = [
    "LocalStorageAdapter",
    "S3R2StorageAdapter",
    "criar_storage_adapter",
]


def criar_storage_adapter(config: Configuracoes) -> StorageMidiaPort:
    """Instancia o provedor de storage configurado conforme ambiente."""
    if config.storage_backend == "s3":
        assert config.storage_bucket is not None
        assert config.storage_access_key_id is not None
        assert config.storage_secret_access_key is not None
        cliente = criar_cliente_s3(
            access_key_id=config.storage_access_key_id.get_secret_value(),
            secret_access_key=config.storage_secret_access_key.get_secret_value(),
            region_name=config.storage_region,
            endpoint_url=config.storage_endpoint_url,
        )
        return S3R2StorageAdapter(
            client=cliente,
            bucket=config.storage_bucket,
            public_base_url=config.storage_public_base_url,
            presigned_ttl_segundos=config.storage_presigned_ttl_segundos,
        )
    return LocalStorageAdapter(
        base_dir=Path(config.storage_local_dir),
        base_url=config.storage_local_base_url,
    )
