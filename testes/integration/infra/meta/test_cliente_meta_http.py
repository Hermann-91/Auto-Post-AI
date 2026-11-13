"""Testes de integração do ClienteMetaHttp (polling backoff e idempotência)."""

from __future__ import annotations

import httpx
import pytest

from app.dominio.excecoes import ErroIntegracaoMeta
from app.infra.meta.cliente_meta_http import ClienteMetaHttp


async def _sem_espera(_seg: float) -> None:
    return None


async def test_polling_backoff_e_falha_container() -> None:
    estados = iter(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cont_1"):
            return httpx.Response(200, json={"status_code": next(estados)})
        if request.url.path.endswith("/cont_err"):
            return httpx.Response(200, json={"status_code": "ERROR", "status": "Codec inválido"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cli:
        cliente = ClienteMetaHttp(
            polling_intervalos=[0.01, 0.01, 0.01], http_client=cli, sleep_fn=_sem_espera
        )
        ok = await cliente.aguardar_container_pronto("cont_1", "tok")
        assert ok.status_code == "FINISHED"

        with pytest.raises(ErroIntegracaoMeta, match="Codec inválido"):
            await cliente.aguardar_container_pronto("cont_err", "tok")


async def test_idempotencia_media_publish_apos_timeout_e_5xx() -> None:
    def handler_timeout(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media_publish"):
            raise httpx.ReadTimeout("timeout", request=request)
        if request.url.path.endswith("/cont_idemp"):
            return httpx.Response(200, json={"status_code": "PUBLISHED"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_timeout)) as cli:
        cliente = ClienteMetaHttp(http_client=cli, sleep_fn=_sem_espera)
        mid = await cliente.publicar_container("17841", "tok", "cont_idemp")
        assert mid == "published:cont_idemp"

    def handler_5xx(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media_publish"):
            return httpx.Response(503, json={"error": {"message": "Temporário"}})
        if request.url.path.endswith("/cont_nao_pub"):
            return httpx.Response(200, json={"status_code": "FINISHED"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_5xx)) as cli:
        cliente = ClienteMetaHttp(http_client=cli, sleep_fn=_sem_espera)
        with pytest.raises(ErroIntegracaoMeta):
            await cliente.publicar_container("17841", "tok", "cont_nao_pub")
