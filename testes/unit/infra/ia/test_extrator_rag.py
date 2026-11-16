"""Testes unitários de extração RAG (.pdf, .txt, .md, URLs públicas e anti-SSRF)."""

from __future__ import annotations

from io import BytesIO

import httpx
import pypdf
import pytest

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.ia.extrator_rag import ExtratorConteudoRag, validar_url_publica_rag


def _criar_pdf_bytes(texto: str) -> bytes:
    escritor = pypdf.PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    stream = pypdf.generic.DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 150 Td ({texto}) Tj ET".encode("latin-1"))
    pagina = escritor.pages[0]
    fonte = pypdf.generic.DictionaryObject(
        {
            pypdf.generic.NameObject("/Type"): pypdf.generic.NameObject("/Font"),
            pypdf.generic.NameObject("/Subtype"): pypdf.generic.NameObject("/Type1"),
            pypdf.generic.NameObject("/BaseFont"): pypdf.generic.NameObject("/Helvetica"),
        }
    )
    recursos = pypdf.generic.DictionaryObject(
        {
            pypdf.generic.NameObject("/Font"): pypdf.generic.DictionaryObject(
                {pypdf.generic.NameObject("/F1"): fonte}
            )
        }
    )
    pagina[pypdf.generic.NameObject("/Resources")] = recursos
    pagina[pypdf.generic.NameObject("/Contents")] = escritor._add_object(stream)
    buf = BytesIO()
    escritor.write(buf)
    return buf.getvalue()


def test_extrair_arquivos_txt_md_pdf_e_rejeitar_invalidos() -> None:
    ext = ExtratorConteudoRag()
    nome_md, txt_md = ext.extrair_arquivo("../../guia.md", b"# Titulo\nConteudo artesanal.")
    assert nome_md == "guia.md" and "Conteudo artesanal." in txt_md

    pdf_bytes = _criar_pdf_bytes("Cardapio Especial Cafe")
    nome_pdf, txt_pdf = ext.extrair_arquivo("cardapio.pdf", pdf_bytes)
    assert nome_pdf == "cardapio.pdf" and "Cardapio Especial Cafe" in txt_pdf

    with pytest.raises(ErroValidacaoDominio):
        ext.extrair_arquivo("script.exe", b"binario")
    with pytest.raises(ErroValidacaoDominio):
        ext.extrair_arquivo("quebrado.pdf", b"nao-eh-pdf")


async def test_validar_url_bloqueia_ssrf_e_extrai_html_limpo() -> None:
    async def resolver_publico(_h: str, _p: int) -> list[str]:
        return ["93.184.216.34"]

    async def resolver_privado(_h: str, _p: int) -> list[str]:
        return ["10.0.0.5"]

    for ruim in (
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost:8000/interno",
        "https://user:pass@exemplo.com",
    ):
        with pytest.raises(ErroValidacaoDominio):
            await validar_url_publica_rag(ruim, resolver_publico)

    with pytest.raises(ErroValidacaoDominio):
        await validar_url_publica_rag("https://rebind.exemplo.com", resolver_privado)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/redir":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/segredo"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>Guia Cafe</title>"
                "<style>body{color:red}</style><script>alert(1)</script></head>"
                "<body><h1>Torra Media</h1><p>Notas de chocolate e caramelo.</p></body></html>"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ext = ExtratorConteudoRag(http_client=client, resolver_ips=resolver_publico)
        titulo, limpo = await ext.extrair_url("https://exemplo.com/guia")
        assert titulo == "Guia Cafe"
        assert "Torra Media" in limpo and "alert(1)" not in limpo

        with pytest.raises(ErroValidacaoDominio):
            await ext.extrair_url("https://exemplo.com/redir")
