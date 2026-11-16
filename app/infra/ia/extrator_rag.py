"""Extração segura de conteúdo RAG (.pdf, .txt, .md e URLs públicas anti-SSRF)."""

from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import urljoin

import httpx
import pypdf

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.ia.extrator_html_ssrf import (
    ExtratorHTMLNativo,
    ResolverIPsFn,
    validar_url_publica_rag,
)

_EXTENSOES_PERMITIDAS = frozenset({"txt", "md", "pdf"})

__all__ = ["ExtratorConteudoRag", "validar_url_publica_rag"]


class ExtratorConteudoRag:
    """Extrai texto limpo de arquivos (.pdf, .txt, .md) e páginas web públicas."""

    def __init__(
        self,
        max_arquivo_bytes: int = 5 * 1024 * 1024,
        max_chars: int = 30000,
        timeout_segundos: float = 15.0,
        http_client: httpx.AsyncClient | None = None,
        resolver_ips: ResolverIPsFn | None = None,
    ) -> None:
        self._max_bytes = max_arquivo_bytes
        self._max_chars = max_chars
        self._timeout = timeout_segundos
        self._http_client = http_client
        self._resolver_ips = resolver_ips

    def _decodificar_texto(self, conteudo_bytes: bytes) -> str:
        try:
            return conteudo_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            return conteudo_bytes.decode("latin-1", errors="replace")

    def _extrair_pdf(self, conteudo_bytes: bytes) -> str:
        try:
            leitor = pypdf.PdfReader(io.BytesIO(conteudo_bytes))
            if leitor.is_encrypted and not leitor.decrypt(""):
                raise ErroValidacaoDominio("PDF protegido por senha não pode ser indexado.")
            paginas = [(pag.extract_text() or "").strip() for pag in leitor.pages]
        except ErroValidacaoDominio:
            raise
        except Exception as exc:
            raise ErroValidacaoDominio("Arquivo PDF inválido ou corrompido.") from exc
        texto = "\n\n".join(p for p in paginas if p)
        if not texto.strip():
            raise ErroValidacaoDominio("PDF não possui texto extraível para indexação RAG.")
        return texto

    def extrair_arquivo(self, nome_arquivo: str, conteudo_bytes: bytes) -> tuple[str, str]:
        """Extrai título seguro e texto limpo de arquivos .txt, .md ou .pdf."""
        nome_seguro = Path(nome_arquivo.strip()).name
        extensao = Path(nome_seguro).suffix.lower().lstrip(".")
        if not nome_seguro or extensao not in _EXTENSOES_PERMITIDAS:
            raise ErroValidacaoDominio("Formato não suportado. Envie arquivos .pdf, .txt ou .md.")
        if not conteudo_bytes or len(conteudo_bytes) > self._max_bytes:
            raise ErroValidacaoDominio("Arquivo vazio ou acima do limite permitido para RAG.")

        bruto = (
            self._extrair_pdf(conteudo_bytes)
            if extensao == "pdf"
            else self._decodificar_texto(conteudo_bytes)
        )
        linhas = [" ".join(ln.split()) for ln in bruto.splitlines()]
        limpo = "\n".join(ln for ln in linhas if ln)[: self._max_chars].strip()
        if not limpo:
            raise ErroValidacaoDominio("Documento sem conteúdo textual aproveitável.")
        return nome_seguro[:240], limpo

    async def _baixar_com_redirects_seguros(self, url_inicial: str) -> httpx.Response:
        atual = await validar_url_publica_rag(url_inicial, self._resolver_ips)
        headers = {"User-Agent": "RoboAutoInst-RAG/1.0 (+https://openrouter.ai)"}
        for _ in range(4):
            if self._http_client is not None:
                resp = await self._http_client.get(
                    atual, headers=headers, follow_redirects=False
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(atual, headers=headers, follow_redirects=False)
            if resp.status_code in {301, 302, 303, 307, 308}:
                destino = resp.headers.get("location", "").strip()
                if not destino:
                    break
                atual = await validar_url_publica_rag(
                    urljoin(atual, destino), self._resolver_ips
                )
                continue
            resp.raise_for_status()
            return resp
        raise ErroValidacaoDominio("Muitos redirecionamentos ao acessar URL informada.")

    async def extrair_url(self, url: str) -> tuple[str, str]:
        """Baixa página web pública validando anti-SSRF e higieniza com HTMLParser."""
        try:
            resp = await self._baixar_com_redirects_seguros(url)
        except httpx.HTTPError as exc:
            raise ErroValidacaoDominio("Falha ao acessar a URL pública informada.") from exc
        if len(resp.content) > self._max_bytes:
            raise ErroValidacaoDominio("Conteúdo da URL excede o limite de tamanho permitido.")

        ctype = resp.headers.get("content-type", "").lower()
        if "pdf" in ctype:
            _, txt_pdf = self.extrair_arquivo("documento.pdf", resp.content)
            return url.strip()[:240], txt_pdf
        if ctype and not any(t in ctype for t in ("text/", "xhtml", "xml")):
            raise ErroValidacaoDominio(
                "Tipo de conteúdo da URL não suportado para leitura RAG."
            )
        if "html" in ctype or not ctype:
            parser = ExtratorHTMLNativo()
            parser.feed(resp.text)
            parser.close()
            titulo, limpo = parser.resultado()
        else:
            titulo, limpo = "", resp.text.strip()

        texto_final = limpo[: self._max_chars].strip()
        if len(texto_final) < 10:
            raise ErroValidacaoDominio("Página web sem conteúdo textual relevante para RAG.")
        return (titulo or str(resp.url))[:240], texto_final
