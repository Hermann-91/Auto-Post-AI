"""Buscador web real de tendências e blueprints abertos por nicho e região."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import httpx

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_HEADERS_WEB = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


class BuscadorWebPort(Protocol):
    async def buscar(self, nicho: str, regiao: str) -> list[dict[str, str]]: ...


def _desembrulhar_url_ddg(href: str) -> str:
    limpa = href.strip()
    if limpa.startswith("//"):
        limpa = f"https:{limpa}"
    analisada = urlparse(limpa)
    if "duckduckgo.com" in (analisada.netloc or "") and analisada.path.startswith("/l/"):
        qs = parse_qs(analisada.query)
        alvo = qs.get("uddg", [""])[0]
        if alvo:
            return alvo
    return limpa


_DOMINIOS_BLOQUEADOS = ("instagram.com", "facebook.com", "fb.com")


def _url_permitida(url: str) -> bool:
    if not url:
        return True
    analisada = urlparse(url.strip())
    dominio = (analisada.hostname or "").lower().rstrip(".")
    if analisada.scheme not in {"http", "https"} or not dominio:
        return False
    return not any(dominio == b or dominio.endswith(f".{b}") for b in _DOMINIOS_BLOQUEADOS)


class _ParserDuckDuckGoHTML(HTMLParser):
    """Extrai títulos, URLs reais e snippets do DuckDuckGo HTML sem regex frágil."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.itens: list[dict[str, str]] = []
        self._titulo_partes: list[str] = []
        self._resumo_partes: list[str] = []
        self._url_atual = ""
        self._em_titulo = False
        self._em_resumo = False

    def _fechar_item(self) -> None:
        titulo = " ".join("".join(self._titulo_partes).split()).strip()
        resumo = " ".join("".join(self._resumo_partes).split()).strip()
        if titulo and self._url_atual and _url_permitida(self._url_atual):
            self.itens.append(
                {
                    "titulo": titulo[:120],
                    "resumo": (resumo or titulo)[:320],
                    "url": self._url_atual[:400],
                }
            )
        self._titulo_partes, self._resumo_partes, self._url_atual = [], [], ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        mapa = dict(attrs)
        classes = set((mapa.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._fechar_item()
            self._url_atual = _desembrulhar_url_ddg(mapa.get("href") or "")
            self._em_titulo = True
        elif "result__snippet" in classes:
            self._em_resumo = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._em_titulo:
            self._em_titulo = False
        elif self._em_resumo and tag in {"a", "div", "span", "td"}:
            self._em_resumo = False

    def handle_data(self, data: str) -> None:
        if self._em_titulo:
            self._titulo_partes.append(data)
        elif self._em_resumo:
            self._resumo_partes.append(data)

    def obter_itens(self) -> list[dict[str, str]]:
        self._fechar_item()
        return self.itens


def _extrair_topicos_rss(xml_bruto: str, limite: int) -> list[dict[str, str]]:
    if "<!DOCTYPE" in xml_bruto.upper() or "<!ENTITY" in xml_bruto.upper():
        return []
    try:
        raiz = ET.fromstring(xml_bruto)
    except ET.ParseError:
        return []
    itens: list[dict[str, str]] = []
    for elem in raiz.findall("./channel/item"):
        if len(itens) >= limite:
            break
        titulo = " ".join((elem.findtext("title") or "").split()).strip()
        link = (elem.findtext("link") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", html.unescape(elem.findtext("description") or ""))
        resumo = " ".join(desc.split()).strip() or titulo
        if titulo and _url_permitida(link):
            itens.append(
                {
                    "titulo": titulo[:120],
                    "resumo": resumo[:320],
                    "url": link[:400],
                    "categoria": "tendencia",
                }
            )
    return itens


class BuscadorWebReal:
    """Busca tendências e blueprints abertos parametrizados por nicho e região."""

    def __init__(
        self,
        base_url: str = "https://html.duckduckgo.com/html/",
        timeout_segundos: float = 10.0,
        max_resultados: int = 6,
        http_client: httpx.AsyncClient | None = None,
        usar_fallback_rss: bool = True,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout_segundos
        self._max_resultados = max_resultados
        self._http_client = http_client
        self._usar_fallback_rss = usar_fallback_rss

    async def _get(self, url: str, params: dict[str, str]) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.get(url, params=params, headers=_HEADERS_WEB)
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            return await client.get(url, params=params, headers=_HEADERS_WEB)

    async def _consultar_ddg_html(self, query: str, categoria: str) -> list[dict[str, str]]:
        resp = await self._get(self._base_url, {"q": query, "kl": "br-pt"})
        resp.raise_for_status()
        parser = _ParserDuckDuckGoHTML()
        parser.feed(resp.text)
        parser.close()
        return [{**item, "categoria": categoria} for item in parser.obter_itens()]

    async def buscar(self, nicho: str, regiao: str) -> list[dict[str, str]]:
        """Consulta tendências do nicho/região e blueprints abertos de formatos."""
        ano = datetime.now(UTC).year
        consultas = [
            (f"{nicho} {regiao} tendencias conteudo {ano}", "tendencia"),
            (f"{nicho} formatos carrossel reels instagram ideias engajamento", "blueprint"),
        ]
        coletados: list[dict[str, str]] = []
        vistos: set[str] = set()
        ultimo_erro: Exception | None = None
        for query, categoria in consultas:
            try:
                achados = await self._consultar_ddg_html(query, categoria)
            except (httpx.HTTPError, ValueError) as exc:
                ultimo_erro = exc
                achados = []
            for item in achados:
                chave = item["url"] or item["titulo"].lower()
                if chave in vistos:
                    continue
                vistos.add(chave)
                coletados.append(item)
                if len(coletados) >= self._max_resultados:
                    return coletados

        if not coletados and self._usar_fallback_rss:
            resp = await self._get(
                _GOOGLE_NEWS_RSS,
                {"q": f"{nicho} {regiao}", "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
            )
            resp.raise_for_status()
            return _extrair_topicos_rss(resp.text, self._max_resultados)
        if not coletados and ultimo_erro is not None:
            raise ultimo_erro
        return coletados
