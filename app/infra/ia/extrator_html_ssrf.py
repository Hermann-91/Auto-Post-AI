"""Parser HTML nativo e validação anti-SSRF para ingestão pública de URLs RAG."""

from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
from urllib.parse import urlparse

from app.dominio.excecoes import ErroValidacaoDominio

_TAGS_IGNORADAS = frozenset({"script", "style", "noscript", "svg", "template"})
_TAGS_BLOCO = frozenset(
    {
        "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr",
        "section", "article", "blockquote", "pre",
    }
)
_HOSTS_BLOQUEADOS = frozenset({"localhost", "0.0.0.0", "metadata.google.internal"})
ResolverIPsFn = Callable[[str, int], Awaitable[list[str]]]


class ExtratorHTMLNativo(HTMLParser):
    """Parser HTML stdlib que descarta scripts/estilos e preserva quebras de bloco."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignorar_nivel = 0
        self._em_title = False
        self._partes_title: list[str] = []
        self._partes_texto: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _ = attrs
        t = tag.lower()
        if t in _TAGS_IGNORADAS:
            self._ignorar_nivel += 1
        elif t == "title" and self._ignorar_nivel == 0:
            self._em_title = True
        elif t in _TAGS_BLOCO and self._ignorar_nivel == 0:
            self._partes_texto.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in _TAGS_IGNORADAS and self._ignorar_nivel > 0:
            self._ignorar_nivel -= 1
        elif t == "title":
            self._em_title = False
        elif t in _TAGS_BLOCO and self._ignorar_nivel == 0:
            self._partes_texto.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignorar_nivel > 0:
            return
        if self._em_title:
            self._partes_title.append(data)
        self._partes_texto.append(data)

    def resultado(self) -> tuple[str, str]:
        titulo = " ".join("".join(self._partes_title).split()).strip()
        bruto = html.unescape("".join(self._partes_texto))
        linhas = [" ".join(ln.split()) for ln in bruto.splitlines()]
        texto = "\n".join(ln for ln in linhas if ln)
        return titulo, re.sub(r"\n{3,}", "\n\n", texto)


def _ip_eh_publico(ip_texto: str) -> bool:
    ip_obj = ipaddress.ip_address(ip_texto)
    return bool(
        ip_obj.is_global
        and not ip_obj.is_private
        and not ip_obj.is_loopback
        and not ip_obj.is_link_local
        and not ip_obj.is_reserved
        and not ip_obj.is_multicast
        and not ip_obj.is_unspecified
    )


async def _resolver_dns_sistema(host: str, porta: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, porta, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos if info[4]]


async def validar_url_publica_rag(url: str, resolver_ips: ResolverIPsFn | None = None) -> str:
    """Valida URL HTTP/HTTPS pública bloqueando redes internas/loopback/link-local."""
    limpa = url.strip()
    if "://" not in limpa:
        limpa = f"https://{limpa}"
    analisada = urlparse(limpa)
    if analisada.scheme not in {"http", "https"} or not analisada.hostname:
        raise ErroValidacaoDominio("Informe uma URL pública HTTP/HTTPS válida.")
    if analisada.username or analisada.password:
        raise ErroValidacaoDominio("URLs com credenciais embutidas não são permitidas.")
    if analisada.port not in {None, 80, 443}:
        raise ErroValidacaoDominio("Apenas portas padrão HTTP/HTTPS (80/443) são permitidas.")
    host = analisada.hostname.lower().rstrip(".")
    if host in _HOSTS_BLOQUEADOS or host.endswith((".local", ".internal", ".localhost")):
        raise ErroValidacaoDominio("Host interno ou local bloqueado por segurança (SSRF).")

    try:
        if not _ip_eh_publico(host):
            raise ErroValidacaoDominio("Endereço IP privado ou reservado bloqueado (SSRF).")
        return limpa
    except ValueError:
        pass

    porta = analisada.port or (443 if analisada.scheme == "https" else 80)
    resolvedor = resolver_ips or _resolver_dns_sistema
    try:
        ips = await resolvedor(host, porta)
    except OSError as exc:
        raise ErroValidacaoDominio("Não foi possível resolver o domínio informado.") from exc
    if not ips or any(not _ip_eh_publico(ip) for ip in ips):
        raise ErroValidacaoDominio("Domínio resolve para endereço não público (bloqueio SSRF).")
    return limpa
