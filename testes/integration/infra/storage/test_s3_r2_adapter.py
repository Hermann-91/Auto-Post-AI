"""Testes de integração do adaptador S3/R2 usando botocore Stubber."""

from __future__ import annotations

from io import BytesIO
from typing import cast

import boto3
import pytest
from botocore.config import Config as BotoConfig
from botocore.response import StreamingBody
from botocore.stub import Stubber
from pydantic import SecretStr

from app.core.config import Configuracoes
from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.storage import S3R2StorageAdapter, criar_storage_adapter
from app.infra.storage.s3_r2_adapter import ClienteS3Port


def _criar_cliente_stub() -> tuple[ClienteS3Port, Stubber]:
    raw_client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
        config=BotoConfig(signature_version="s3v4"),
    )
    return cast(ClienteS3Port, raw_client), Stubber(raw_client)


async def test_s3_r2_enviar_url_cdn_e_remover_com_stubber() -> None:
    cliente, stubber = _criar_cliente_stub()
    chave = "emp/conta/originais/foto.jpg"
    stubber.add_response(
        "put_object",
        {"ETag": '"abc"'},
        {"Bucket": "meu-bucket", "Key": chave, "Body": b"jpeg-bytes", "ContentType": "image/jpeg"},
    )
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(BytesIO(b"jpeg-bytes"), len(b"jpeg-bytes"))},
        {"Bucket": "meu-bucket", "Key": chave},
    )
    stubber.add_response("delete_object", {}, {"Bucket": "meu-bucket", "Key": chave})

    adapter = S3R2StorageAdapter(
        client=cliente, bucket="meu-bucket", public_base_url="https://cdn.exemplo.com/"
    )
    with stubber:
        url = await adapter.enviar_bytes(chave, b"jpeg-bytes", "image/jpeg")
        assert url == f"https://cdn.exemplo.com/{chave}"
        assert await adapter.baixar_bytes(chave) == b"jpeg-bytes"
        await adapter.remover_objeto(chave)
    stubber.assert_no_pending_responses()


async def test_s3_r2_presigned_url_e_validacao_chave() -> None:
    cliente, _ = _criar_cliente_stub()
    adapter = S3R2StorageAdapter(client=cliente, bucket="meu-bucket", presigned_ttl_segundos=900)

    url = await adapter.obter_url_publica("emp/conta/processadas/video.mp4")
    assert "X-Amz-Signature=" in url and "X-Amz-Expires=900" in url

    with pytest.raises(ErroValidacaoDominio):
        await adapter.enviar_bytes("../segredo.txt", b"x", "text/plain")


def test_factory_cria_s3_adapter_quando_configurado() -> None:
    cfg = Configuracoes(
        app_env="dev",
        storage_backend="s3",
        storage_bucket="bucket-r2",
        storage_endpoint_url="https://conta.r2.cloudflarestorage.com",
        storage_access_key_id=SecretStr("key"),
        storage_secret_access_key=SecretStr("secret"),
    )
    adapter = criar_storage_adapter(cfg)
    assert isinstance(adapter, S3R2StorageAdapter)
