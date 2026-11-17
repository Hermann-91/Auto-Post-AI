"""Testes de integração para o polimento das abas secundárias, CSP e empty states (Fase 4)."""

from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.core.config import Configuracoes
from app.main import criar_app


async def test_abas_secundarias_kpis_editor_json_e_csp() -> None:
    cfg = Configuracoes(
        app_env="test",
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
    )
    app = criar_app(cfg)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as cli:
        html = await cli.get("/painel/")
        assert html.status_code == 200
        assert "/painel/css/paineis.css" in html.text
        assert "custos-kpis-grid" in html.text and "custos-periodo-badge" in html.text
        assert "config-json-grid" in html.text and "rag-ingestao-grid" in html.text
        for legado in ("◐", "⚙", "↗", "⚡", "✨"):
            assert legado not in html.text
        assert "https://" not in html.text and "http://" not in html.text

        rotas = (
            "/painel/css/styles.css",
            "/painel/css/paineis.css",
            "/painel/js/auth.js",
            "/painel/js/biblioteca.js",
            "/painel/js/config_custos.js",
            "/painel/js/rag.js",
            "/painel/js/icones.js",
            "/painel/js/componentes/custos_kpi.js",
            "/painel/js/componentes/editor_json_config.js",
            "/painel/js/componentes/estado_vazio.js",
            "/painel/js/componentes/agenda_filtros.js",
        )
        resps = {r: await cli.get(r) for r in rotas}
        assert all(resp.status_code == 200 for resp in resps.values())
        t = {r: resp.text for r, resp in resps.items()}

        kpi = t["/painel/js/componentes/custos_kpi.js"]
        assert "Gasto da Empresa" in kpi and "Saldo Disponível" in kpi
        assert "Bloqueio estrito" in kpi and "Fallback gratuito" in kpi

        ed = t["/painel/js/componentes/editor_json_config.js"]
        assert "json-editor-textarea" in ed and "JSON válido" in ed
        assert "JSON inválido" in ed and "Formatar" in ed

        vazio = t["/painel/js/componentes/estado_vazio.js"]
        assert "empty-state-box" in vazio
        mods_vazio = (
            "/painel/js/biblioteca.js",
            "/painel/js/rag.js",
            "/painel/js/componentes/agenda_filtros.js",
        )
        for mod in mods_vazio:
            assert "criarEstadoVazio" in t[mod]

        paineis = t["/painel/css/paineis.css"]
        assert ".kpis-grid" in paineis and ".json-editor-textarea" in paineis
        assert ".rag-ingestao-grid" in paineis and "@media (max-width: 640px)" in paineis
        assert "min(100%, 300px)" in t["/painel/css/styles.css"]
        assert "progress-warn" in t["/painel/css/styles.css"]

        ic = t["/painel/js/icones.js"]
        icones_esperados = (
            "heart", "bookOpen", "globe", "fileText",
            "dollarSign", "shield", "database", "code", "externalLink",
        )
        for nome in icones_esperados:
            assert nome in ic

        exts = {".html", ".js", ".css"}
        arquivos_front = [
            p for p in Path("frontend").rglob("*") if p.is_file() and p.suffix in exts
        ]
        assert arquivos_front
        for arq in arquivos_front:
            conteudo = arq.read_text(encoding="utf-8")
            assert "innerHTML" not in conteudo, f"innerHTML proibido encontrado em {arq}"
            assert len(conteudo.splitlines()) <= 200, f"{arq} excede 200 linhas"
