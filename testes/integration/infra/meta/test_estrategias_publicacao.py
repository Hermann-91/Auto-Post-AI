"""Testes de integração das estratégias Meta (IMAGE, CAROUSEL, REELS, STORIES)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroLimitePublicacaoMeta, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoMidia
from app.infra.meta import ClienteMetaHttp, FabricaPublicadoresMeta


async def _sem_espera(_seg: float) -> None:
    return None


def _conta_teste() -> ContaInstagram:
    return ContaInstagram(
        empresa_id=uuid4(),
        ig_user_id="1784100",
        username="conta_dev",
        access_token_enc="enc",
        token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )


async def test_estrategias_quatro_formatos_e_payloads_oficiais() -> None:
    payloads_media: list[dict[str, Any]] = []
    seq = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/content_publishing_limit"):
            return httpx.Response(
                200, json={"data": [{"quota_usage": 2, "config": {"quota_total": 50}}]}
            )
        if request.url.path.endswith("/media"):
            seq["n"] += 1
            payloads_media.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"id": f"cont_{seq['n']}"})
        if request.url.path.endswith("/media_publish"):
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"id": f"pub_{body['creation_id']}"})
        if "/cont_" in request.url.path:
            return httpx.Response(200, json={"status_code": "FINISHED"})
        return httpx.Response(404)

    conta = _conta_teste()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cli:
        fabrica = FabricaPublicadoresMeta(
            ClienteMetaHttp(polling_intervalos=[0.01], http_client=cli, sleep_fn=_sem_espera),
            exigir_https=True,
        )

        # 1. IMAGE
        p_img = Postagem(
            empresa_id=conta.empresa_id, conta_ig_id=conta.id,
            tipo_midia=TipoMidia.IMAGE, midias_chaves=["a.jpg"], legenda="Foto!",
        )
        m_img, c_img = await fabrica.obter(TipoMidia.IMAGE).publicar(
            conta, "tok", p_img, ["https://cdn.site/a.jpg"]
        )
        assert (m_img, c_img) == ("pub_cont_1", "cont_1")

        # 2. CAROUSEL (1 imagem + 1 vídeo)
        p_car = Postagem(
            empresa_id=conta.empresa_id, conta_ig_id=conta.id,
            tipo_midia=TipoMidia.CAROUSEL, midias_chaves=["1.jpg", "2.mp4"], legenda="Carrossel!",
        )
        m_car, c_car = await fabrica.obter(TipoMidia.CAROUSEL).publicar(
            conta, "tok", p_car, ["https://cdn.site/1.jpg", "https://cdn.site/2.mp4"]
        )
        assert m_car == "pub_cont_4" and c_car == "cont_4"
        assert payloads_media[1]["is_carousel_item"] is True
        assert payloads_media[2]["media_type"] == "VIDEO"
        assert payloads_media[3]["children"] == ["cont_2", "cont_3"]

        # 3. REELS
        p_reels = Postagem(
            empresa_id=conta.empresa_id, conta_ig_id=conta.id,
            tipo_midia=TipoMidia.REELS, midias_chaves=["v.mp4"], legenda="Reels!",
        )
        m_reels, _ = await fabrica.obter(TipoMidia.REELS).publicar(
            conta, "tok", p_reels, ["https://cdn.site/v.mp4"]
        )
        assert m_reels == "pub_cont_5" and payloads_media[4]["media_type"] == "REELS"

        # 4. STORIES (sem caption)
        p_sto = Postagem(
            empresa_id=conta.empresa_id, conta_ig_id=conta.id,
            tipo_midia=TipoMidia.STORIES, midias_chaves=["s.jpg"], legenda="",
        )
        m_sto, _ = await fabrica.obter(TipoMidia.STORIES).publicar(
            conta, "tok", p_sto, ["https://cdn.site/s.jpg"]
        )
        assert m_sto == "pub_cont_6" and "caption" not in payloads_media[5]

        # Validação HTTPS em produção
        with pytest.raises(ErroValidacaoDominio):
            await fabrica.obter(TipoMidia.IMAGE).publicar(
                conta, "tok", p_img, ["http://inseguro.local/a.jpg"]
            )


async def test_cota_meta_atingida_aborta_antes_de_criar_container() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/content_publishing_limit"):
            return httpx.Response(
                200, json={"data": [{"quota_usage": 50, "config": {"quota_total": 50}}]}
            )
        raise AssertionError("Não deve criar container quando cota atingida.")

    conta = _conta_teste()
    p_img = Postagem(
        empresa_id=conta.empresa_id, conta_ig_id=conta.id,
        tipo_midia=TipoMidia.IMAGE, midias_chaves=["a.jpg"],
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cli:
        fabrica = FabricaPublicadoresMeta(ClienteMetaHttp(http_client=cli, sleep_fn=_sem_espera))
        with pytest.raises(ErroLimitePublicacaoMeta):
            await fabrica.obter(TipoMidia.IMAGE).publicar(
                conta, "tok", p_img, ["https://cdn.site/a.jpg"]
            )
