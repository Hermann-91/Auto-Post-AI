"""Adaptador Cloudflare R2 / AWS S3 compatível com StorageMidiaPort."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, cast

import boto3
from botocore.config import Config as BotoConfig

from app.dominio.excecoes import ErroValidacaoDominio


class ClienteS3Port(Protocol):
    """Subconjunto tipado do cliente boto3 S3 para injeção e testes."""

    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def delete_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def generate_presigned_url(
        self,
        ClientMethod: str,
        Params: dict[str, Any] | None = None,
        ExpiresIn: int = 3600,
    ) -> str: ...


def criar_cliente_s3(
    access_key_id: str,
    secret_access_key: str,
    region_name: str = "auto",
    endpoint_url: str | None = None,
) -> ClienteS3Port:
    """Cria cliente boto3 S3 com SigV4 compatível com Cloudflare R2 e AWS S3."""
    cliente = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_name,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=BotoConfig(signature_version="s3v4"),
    )
    return cast(ClienteS3Port, cliente)


def _normalizar_chave(chave: str) -> str:
    limpa = chave.strip().lstrip("/")
    if not limpa or ".." in limpa.split("/"):
        raise ErroValidacaoDominio("Chave de objeto inválida para storage R2/S3.")
    return limpa


class S3R2StorageAdapter:
    """Armazena, expõe via HTTPS público e remove mídias em bucket R2/S3."""

    def __init__(
        self,
        client: ClienteS3Port,
        bucket: str,
        public_base_url: str | None = None,
        presigned_ttl_segundos: int = 3600,
    ) -> None:
        if not bucket.strip():
            raise ErroValidacaoDominio("Nome do bucket R2/S3 é obrigatório.")
        self._client = client
        self._bucket = bucket.strip()
        self._public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self._presigned_ttl = presigned_ttl_segundos

    async def enviar_bytes(self, chave: str, conteudo: bytes, content_type: str) -> str:
        chave_limpa = _normalizar_chave(chave)
        if not conteudo:
            raise ErroValidacaoDominio("Conteúdo do arquivo não pode ser vazio.")
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=chave_limpa,
            Body=conteudo,
            ContentType=content_type,
        )
        return await self.obter_url_publica(chave_limpa)

    async def obter_url_publica(self, chave: str) -> str:
        chave_limpa = _normalizar_chave(chave)
        if self._public_base_url:
            return f"{self._public_base_url}/{chave_limpa}"
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": chave_limpa},
            ExpiresIn=self._presigned_ttl,
        )

    async def remover_objeto(self, chave: str) -> None:
        chave_limpa = _normalizar_chave(chave)
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=chave_limpa,
        )
