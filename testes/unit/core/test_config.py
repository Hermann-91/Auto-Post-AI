"""Testes unitários das configurações e validação fail-fast de produção."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from app.core.config import Configuracoes


def test_producao_exige_jwt_fernet_e_cookie_seguro() -> None:
    with pytest.raises(ValidationError):
        Configuracoes(app_env="prod", cookie_secure=True)


def test_producao_exige_turnstile_secret_quando_captcha_ativo() -> None:
    chave_fernet = Fernet.generate_key().decode("utf-8")
    with pytest.raises(ValidationError):
        Configuracoes(
            app_env="prod",
            jwt_secret_key=SecretStr("x" * 40),
            fernet_keys=SecretStr(chave_fernet),
            captcha_enabled=True,
            turnstile_secret_key=None,
            cookie_secure=True,
        )


def test_dev_gera_chaves_efemeras_consistentes() -> None:
    cfg = Configuracoes(app_env="dev")
    jwt1 = cfg.resolver_jwt_secret()
    jwt2 = cfg.resolver_jwt_secret()
    fernet = cfg.resolver_fernet_keys()

    assert jwt1 == jwt2
    assert len(jwt1) >= 32
    assert len(fernet) == 1


def test_producao_exige_database_url_e_storage_s3() -> None:
    chave_fernet = Fernet.generate_key().decode("utf-8")
    with pytest.raises(ValidationError):
        Configuracoes(
            app_env="prod",
            jwt_secret_key=SecretStr("x" * 40),
            fernet_keys=SecretStr(chave_fernet),
            cookie_secure=True,
            database_url=None,
            storage_backend="s3",
        )
    with pytest.raises(ValidationError):
        Configuracoes(app_env="dev", storage_backend="s3", storage_bucket=None)


def test_resolver_database_url_usa_fallback_sqlite_fora_de_producao() -> None:
    cfg_dev = Configuracoes(app_env="dev")
    assert cfg_dev.resolver_database_url().startswith("sqlite+aiosqlite:///")
    cfg_custom = Configuracoes(
        app_env="test", database_url=SecretStr("postgresql+asyncpg://u:p@db:5432/app")
    )
    assert cfg_custom.resolver_database_url() == "postgresql+asyncpg://u:p@db:5432/app"
