"""Testes unitários do adaptador HTTP OpenRouter (texto, visão e Nano Banana)."""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.dominio.excecoes import ErroIntegracaoIA, ErroValidacaoDominio
from app.infra.ia.cliente_openrouter import ClienteIANaoConfigurado, ClienteOpenRouter


def _transport_por_rotas(
    handler: Any,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_gerar_texto_json_e_extrair_custo_real() -> None:
    capturado: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        capturado["auth"] = req.headers.get("authorization")
        capturado["body"] = json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "id": "gen-abc123",
                "model": "deepseek/deepseek-v4-flash",
                "choices": [{"message": {"content": '{"legenda": "Olá"}'}}],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 45,
                    "cost": 0.001234,
                    "prompt_tokens_details": {"cached_tokens": 20},
                },
            },
        )

    async with _transport_por_rotas(handler) as http_client:
        cli = ClienteOpenRouter(api_key="sk-test", http_client=http_client)
        texto, usage = await cli.gerar_texto(
            "sys", "user", "deepseek/deepseek-v4-flash", formato_json=True
        )

    assert texto == '{"legenda": "Olá"}'
    assert capturado["auth"] == "Bearer sk-test"
    assert capturado["body"]["response_format"] == {"type": "json_object"}
    assert usage["openrouter_gen_id"] == "gen-abc123"
    assert usage["tokens_in"] == 120
    assert usage["tokens_out"] == 45
    assert usage["tokens_cached"] == 20
    assert usage["custo_usd"] == Decimal("0.001234")


async def test_fallback_automatico_para_free_em_429_e_sem_fallback_quando_ja_free() -> None:
    modelos_chamados: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        modelos_chamados.append(body["model"])
        if body["model"] == "deepseek/deepseek-v4-flash":
            return httpx.Response(429, json={"error": "rate limit"})
        if body["model"] == "modelo/custom:free":
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(
            200,
            json={
                "id": "gen-fb",
                "model": "openrouter/free",
                "choices": [{"message": {"content": "ok free"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0},
            },
        )

    async with _transport_por_rotas(handler) as http_client:
        cli = ClienteOpenRouter(api_key="sk-test", http_client=http_client)
        texto, usage = await cli.gerar_texto("s", "u", "deepseek/deepseek-v4-flash")
        assert texto == "ok free"
        assert usage["modelo"] == "openrouter/free"
        assert modelos_chamados == ["deepseek/deepseek-v4-flash", "openrouter/free"]

        with pytest.raises(ErroIntegracaoIA):
            await cli.gerar_texto("s", "u", "modelo/custom:free")


async def test_nano_banana_gera_e_edita_imagem_base64() -> None:
    payloads: list[dict[str, Any]] = []
    png_fake = b"\x89PNG\r\n\x1a\nconteudo"
    b64_saida = base64.b64encode(png_fake).decode("ascii")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/generation"):
            return httpx.Response(200, json={"data": {"id": "gen-img", "total_cost": 0.03}})
        payloads.append(json.loads(req.content))
        return httpx.Response(
            200,
            json={
                "id": "gen-img",
                "model": "google/gemini-3.1-flash-image",
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "images": [
                                {"image_url": {"url": f"data:image/png;base64,{b64_saida}"}}
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 1200, "cost": 0.0315},
            },
        )

    async with _transport_por_rotas(handler) as http_client:
        cli = ClienteOpenRouter(api_key="sk-test", http_client=http_client)
        img, usage = await cli.gerar_ou_editar_imagem(
            prompt="Café artesanal na mesa",
            modelo="google/gemini-3.1-flash-image",
            imagem_base_url="data:image/jpeg;base64,/9j/4AAQ",
        )
        auditoria = await cli.consultar_geracao("gen-img")

    assert img == png_fake
    assert usage["custo_usd"] == Decimal("0.031500")
    assert payloads[0]["modalities"] == ["image", "text"]
    assert payloads[0]["messages"][0]["content"][1]["type"] == "image_url"
    assert auditoria["total_cost"] == 0.03


async def test_visao_rejeita_ssrf_http_e_stub_nao_configurado_falha() -> None:
    cli = ClienteOpenRouter(api_key="sk-test")
    with pytest.raises(ErroValidacaoDominio):
        await cli.analisar_imagem("s", "u", "http://169.254.169.254/latest", "vision")

    nao_cfg = ClienteIANaoConfigurado()
    with pytest.raises(ErroValidacaoDominio):
        await nao_cfg.gerar_texto("s", "u", "deepseek/deepseek-v4-flash")
    with pytest.raises(ErroValidacaoDominio):
        await nao_cfg.gerar_embeddings(["ola"], "openai/text-embedding-3-small")


async def test_openrouter_gera_embeddings_ordenados_e_extrai_custo() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/embeddings")
        return httpx.Response(
            200,
            json={
                "id": "emb-1",
                "model": "openai/text-embedding-3-small",
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 18, "cost": 0.000012},
            },
        )

    async with _transport_por_rotas(handler) as http_client:
        cli = ClienteOpenRouter(api_key="sk-test", http_client=http_client)
        vetores, usage = await cli.gerar_embeddings(
            ["primeiro", "segundo"], "openai/text-embedding-3-small"
        )

    assert vetores == [[1.0, 0.0], [0.0, 1.0]]
    assert usage["tokens_in"] == 18
    assert usage["tokens_out"] == 0
    assert usage["custo_usd"] == Decimal("0.000012")
