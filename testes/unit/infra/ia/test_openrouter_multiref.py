"""Testes unitários de múltiplas referências visuais e anti-SSRF no OpenRouter."""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.ia.cliente_openrouter import ClienteIANaoConfigurado, ClienteOpenRouter
from app.infra.ia.openrouter_parser import montar_payload_imagem


def test_montar_payload_imagem_deduplica_e_valida_ssrf() -> None:
    payload = montar_payload_imagem(
        prompt="Produto sobre mesa de madeira",
        modelo="google/gemini-3.1-flash-image",
        imagem_base_url="data:image/jpeg;base64,/9j/4AAQ",
        imagens_referencia_urls=[
            "data:image/jpeg;base64,/9j/4AAQ",
            "https://cdn.exemplo.com/foto2.jpg",
        ],
    )
    conteudo = payload["messages"][0]["content"]
    assert len(conteudo) == 3
    assert conteudo[0] == {"type": "text", "text": "Produto sobre mesa de madeira"}
    assert conteudo[1]["image_url"]["url"].startswith("data:image/jpeg")
    assert conteudo[2]["image_url"]["url"] == "https://cdn.exemplo.com/foto2.jpg"

    for url_ruim in (
        "http://127.0.0.1/interno.jpg",
        "https://127.0.0.1/interno.jpg",
        "https://169.254.169.254/latest/meta-data",
        "https://localhost:8443/segredo.jpg",
        "https://user:pass@cdn.exemplo.com/foto.jpg",
    ):
        with pytest.raises(ErroValidacaoDominio):
            montar_payload_imagem(
                prompt="Teste SSRF", modelo="google/gemini-3.1-flash-image",
                imagens_referencia_urls=[url_ruim],
            )


async def test_cliente_openrouter_envia_multiplas_referencias_reais() -> None:
    capturado: dict[str, Any] = {}
    png_fake = b"\x89PNG\r\n\x1a\nsaida"
    b64_saida = base64.b64encode(png_fake).decode("ascii")

    def handler(req: httpx.Request) -> httpx.Response:
        capturado["body"] = json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "id": "gen-multiref",
                "model": "google/gemini-3.1-flash-image",
                "choices": [{
                    "message": {
                        "content": "",
                        "images": [{"image_url": {"url": f"data:image/png;base64,{b64_saida}"}}],
                    }
                }],
                "usage": {"prompt_tokens": 90, "completion_tokens": 800, "cost": 0.041},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        cli = ClienteOpenRouter(api_key="sk-test", http_client=http_client)
        img, usage = await cli.gerar_imagem_com_referencias(
            prompt="Preservar rótulo da garrafa",
            modelo="google/gemini-3.1-flash-image",
            imagens_base_urls=[
                "data:image/jpeg;base64,/9j/111",
                "data:image/jpeg;base64,/9j/222",
            ],
        )

    assert img == png_fake
    assert usage["custo_usd"] == Decimal("0.041000")
    content = capturado["body"]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["text", "image_url", "image_url"]

    stub = ClienteIANaoConfigurado()
    with pytest.raises(ErroValidacaoDominio):
        await stub.gerar_imagem_com_referencias("p", "m", ["data:image/jpeg;base64,/9j/111"])
