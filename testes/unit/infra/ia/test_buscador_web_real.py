"""Testes unitários do BuscadorWebReal (DuckDuckGo HTML + fallback RSS seguro)."""

from __future__ import annotations

import httpx

from app.infra.ia.buscador_web_real import BuscadorWebReal


async def test_buscador_web_real_parseia_html_desembrulha_url_e_filtra_instagram() -> None:
    html_ddg = """
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Finstagram.com%2Fp%2F1">
        Post IG bloqueado
      </a>
      <a class="result__snippet">Nao deve aparecer</a>
    </div>
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fblog.ex.com%2Fcafe">
        Tendencias Cafeteria 2026
      </a>
      <a class="result__snippet">Cold brew e carrosseis educativos crescem.</a>
    </div>
    """

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_ddg)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        buscador = BuscadorWebReal(http_client=client, max_resultados=4)
        itens = await buscador.buscar("Cafeteria Especial", "Curitiba")

    assert len(itens) == 1
    assert itens[0]["titulo"] == "Tendencias Cafeteria 2026"
    assert itens[0]["url"] == "https://blog.ex.com/cafe"
    assert "Cold brew" in itens[0]["resumo"]


async def test_buscador_web_real_usa_fallback_rss_e_ignora_xxe() -> None:
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item>
      <title>Alta no mercado de pilates</title>
      <link>https://noticias.ex.com/pilates</link>
      <description>&lt;b&gt;Estudios&lt;/b&gt; crescem no Brasil.</description>
    </item></channel></rss>"""

    def handler(req: httpx.Request) -> httpx.Response:
        if "news.google.com" in str(req.url):
            return httpx.Response(200, text=rss_xml)
        return httpx.Response(200, text="<html><body>sem resultados</body></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        buscador = BuscadorWebReal(http_client=client, max_resultados=4)
        itens = await buscador.buscar("Pilates", "São Paulo")

    assert len(itens) == 1
    assert itens[0]["titulo"] == "Alta no mercado de pilates"
    assert itens[0]["resumo"] == "Estudios crescem no Brasil."
