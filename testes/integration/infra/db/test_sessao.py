"""Testes de integração da sessão SQLAlchemy Async e migrações Alembic."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from pydantic import SecretStr

from app.core.config import Configuracoes
from app.infra.db.sessao import DateTimeUTC, criar_engine_async, verificar_saude_banco


def test_datetime_utc_normaliza_naive_e_fuso_diferente() -> None:
    tipo = DateTimeUTC()
    naive = datetime(2026, 11, 13, 12, 0, 0)
    fuso_br = datetime(2026, 11, 13, 9, 0, 0, tzinfo=timezone(timedelta(hours=-3)))
    esperado = datetime(2026, 11, 13, 12, 0, 0, tzinfo=UTC)

    assert tipo.process_bind_param(naive, None) == esperado  # type: ignore[arg-type]
    assert tipo.process_result_value(fuso_br, None) == esperado  # type: ignore[arg-type]
    assert tipo.process_bind_param(None, None) is None  # type: ignore[arg-type]


async def test_verificar_saude_banco_sqlite(tmp_path: Path) -> None:
    cfg = Configuracoes(
        app_env="test",
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path}/saude.db"),
    )
    engine = criar_engine_async(cfg)
    try:
        assert await verificar_saude_banco(engine) is True
    finally:
        await engine.dispose()


def test_alembic_upgrade_e_downgrade_criam_todas_tabelas(tmp_path: Path) -> None:
    db_file = tmp_path / "migracao.db"
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_file}")

    command.upgrade(alembic_cfg, "head")

    with sqlite3.connect(db_file) as conn:
        tabelas = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        cols_cfg = {
            row[1]
            for row in conn.execute("PRAGMA table_info(configs_ia_conta)").fetchall()
        }
        cols_rag = {row[1] for row in conn.execute("PRAGMA table_info(fontes_rag)").fetchall()}
        cols_post = {row[1] for row in conn.execute("PRAGMA table_info(postagens)").fetchall()}
    esperadas = {
        "empresas",
        "usuarios",
        "refresh_tokens",
        "contas_instagram",
        "configs_ia_conta",
        "fontes_rag",
        "midias_biblioteca",
        "planejamentos_semanais",
        "postagens",
        "registros_custo_ia",
        "alembic_version",
    }
    assert esperadas.issubset(tabelas)
    assert "brand_bible_json" in cols_cfg
    assert {"resumo_fatos", "embeddings_chunks_json"}.issubset(cols_rag)
    assert {"tentativas_publicacao", "atualizado_em"}.issubset(cols_post)

    command.downgrade(alembic_cfg, "base")
    with sqlite3.connect(db_file) as conn:
        restantes = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "empresas" not in restantes
