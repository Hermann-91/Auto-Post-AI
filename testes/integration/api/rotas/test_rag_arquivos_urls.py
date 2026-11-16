"""Testes de integração HTTP para RAG (arquivos/URLs), Brand Bible e isolamento."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pypdf
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Configuracoes
from app.dominio.entidades.tenant import ContaInstagram
from app.infra.ia.extrator_rag import ExtratorConteudoRag
from app.main import criar_app


def _pdf_simples() -> bytes:
    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    stream = pypdf.generic.DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 150 Td (Manual Operacional 2026) Tj ET")
    fonte = pypdf.generic.DictionaryObject(
        {
            pypdf.generic.NameObject("/Type"): pypdf.generic.NameObject("/Font"),
            pypdf.generic.NameObject("/Subtype"): pypdf.generic.NameObject("/Type1"),
            pypdf.generic.NameObject("/BaseFont"): pypdf.generic.NameObject("/Helvetica"),
        }
    )
    w.pages[0][pypdf.generic.NameObject("/Resources")] = pypdf.generic.DictionaryObject(
        {
            pypdf.generic.NameObject("/Font"): pypdf.generic.DictionaryObject(
                {pypdf.generic.NameObject("/F1"): fonte}
            )
        }
    )
    w.pages[0][pypdf.generic.NameObject("/Contents")] = w._add_object(stream)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


class _FakeEmbAPI:
    async def gerar_embeddings(
        self, textos: list[str], modelo: str
    ) -> tuple[list[list[float]], dict[str, Any]]:
        return [[0.5, 0.5] for _ in textos], {
            "openrouter_gen_id": "g-emb",
            "modelo": modelo,
            "tokens_in": 15,
            "tokens_out": 0,
            "custo_usd": Decimal("0.0001"),
        }


async def _criar_usuario_e_conta(
    app: FastAPI, cli: AsyncClient, email: str, username: str
) -> UUID:
    reg = await cli.post(
        "/auth/register",
        json={
            "nome_empresa": f"Emp {username}",
            "email": email,
            "senha": "SenhaSuperSegura#1",
            "turnstile_token": "ok",
        },
    )
    assert reg.status_code == 201
    emp_id = UUID(reg.json()["usuario"]["empresa_id"])
    conta = await app.state.ia_container.conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp_id,
            ig_user_id=f"ig-{username}",
            username=username,
            access_token_enc="tok",
            token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    return UUID(str(conta.id))


async def test_endpoints_rag_arquivo_url_brand_bible_e_isolamento(tmp_path: Path) -> None:
    cfg = Configuracoes(
        app_env="test",
        cors_origens=["https://painel.exemplo.com"],
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
        storage_local_dir=str(tmp_path / "media"),
    )
    app = criar_app(cfg)

    async def resolver_pub(_h: str, _p: int) -> list[str]:
        return ["93.184.216.34"]

    def handler_web(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                "<html><title>Artigo</title>"
                "<body><p>Guia oficial de vendas.</p></body></html>"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_web)) as http_ext:
        app.state.ia_container.extrator_rag = ExtratorConteudoRag(
            http_client=http_ext, resolver_ips=resolver_pub
        )
        app.state.ia_container.cliente_embeddings = _FakeEmbAPI()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://t") as cli_a:
            conta_a = await _criar_usuario_e_conta(app, cli_a, "a@emp.com", "conta_a")

            up_pdf = await cli_a.post(
                f"/contas/{conta_a}/rag/arquivo",
                data={"tipo": "DOCUMENTO", "titulo": "Manual PDF"},
                files={"arquivo": ("manual.pdf", _pdf_simples(), "application/pdf")},
            )
            assert up_pdf.status_code == 201
            assert up_pdf.json()["tem_embeddings"] is True

            up_url = await cli_a.post(
                f"/contas/{conta_a}/rag/url",
                json={"url": "https://exemplo.com/artigo", "tipo": "REFERENCIA_BENCHMARK"},
            )
            assert up_url.status_code == 201
            assert up_url.json()["tipo"] == "REFERENCIA_BENCHMARK"

            ssrf = await cli_a.post(
                f"/contas/{conta_a}/rag/url",
                json={"url": "http://127.0.0.1/interno", "tipo": "URL"},
            )
            assert ssrf.status_code == 422

            comp = await cli_a.post(
                f"/contas/{conta_a}/brand-bible/compilar",
                json={"usar_ia": False},
            )
            assert comp.status_code == 200
            assert len(comp.json()["brand_bible_json"]["fatos_chave_rag"]) == 2

        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://t") as cli_b:
            await _criar_usuario_e_conta(app, cli_b, "b@emp.com", "conta_b")
            negado = await cli_b.get(f"/contas/{conta_a}/rag")
            assert negado.status_code == 422
