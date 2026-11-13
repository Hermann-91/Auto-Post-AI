"""Configurações centralizadas da aplicação com validação fail-fast."""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Configuracoes(BaseSettings):
    """Parâmetros de ambiente da API, segurança, cookies e integrações."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_nome: str = "Robo-Auto-Inst API"
    app_env: Literal["dev", "test", "prod"] = "dev"
    cors_origens: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Segredos (obrigatórios via ambiente em produção; efêmeros apenas em dev/test)
    jwt_secret_key: SecretStr | None = None
    fernet_keys: SecretStr | None = None
    jwt_algoritmo: str = "HS256"
    jwt_issuer: str = "robo-auto-inst"
    jwt_audience: str = "robo-auto-inst-api"
    access_token_minutos: int = Field(default=15, ge=1, le=60)
    refresh_token_dias: int = Field(default=7, ge=1, le=90)

    # Parâmetros Argon2id (OWASP)
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_memory_cost_kib: int = Field(default=65536, ge=8192)
    argon2_parallelism: int = Field(default=4, ge=1)

    # Cookies & Proteção de Entrada
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_access_nome: str = "access_token"
    cookie_refresh_nome: str = "refresh_token"
    rate_limit_max_tentativas: int = Field(default=5, ge=1)
    rate_limit_janela_segundos: int = Field(default=900, ge=10)
    redis_url: str | None = None

    # Cloudflare Turnstile
    captcha_enabled: bool = False
    turnstile_secret_key: SecretStr | None = None
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    turnstile_timeout_segundos: float = Field(default=5.0, ge=1.0, le=30.0)

    # Chaves efêmeras geradas apenas fora de produção quando não informadas
    _jwt_efemero: str | None = None
    _fernet_efemero: str | None = None

    @model_validator(mode="after")
    def validar_seguranca_producao(self) -> Configuracoes:
        """Bloqueia inicialização em produção sem segredos e configurações rígidas."""
        if self.app_env == "prod":
            if self.jwt_secret_key is None or len(self.jwt_secret_key.get_secret_value()) < 32:
                raise ValueError("JWT_SECRET_KEY (>= 32 chars) é obrigatória em produção.")
            if self.fernet_keys is None or not self.fernet_keys.get_secret_value().strip():
                raise ValueError("FERNET_KEYS é obrigatória em produção.")
            if self.captcha_enabled and self.turnstile_secret_key is None:
                raise ValueError("TURNSTILE_SECRET_KEY é obrigatória com CAPTCHA_ENABLED=true.")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE=True é obrigatório em produção.")
        return self

    def resolver_jwt_secret(self) -> str:
        """Retorna a chave JWT configurada ou uma chave efêmera apenas em dev/test."""
        if self.jwt_secret_key is not None:
            return self.jwt_secret_key.get_secret_value()
        if self._jwt_efemero is None:
            logger.warning("Usando JWT_SECRET_KEY efêmera (permitido apenas em dev/test).")
            self._jwt_efemero = secrets.token_urlsafe(48)
        return self._jwt_efemero

    def resolver_fernet_keys(self) -> list[str]:
        """Retorna lista de chaves Fernet (suporte a rotação via MultiFernet)."""
        if self.fernet_keys is not None:
            bruto = self.fernet_keys.get_secret_value()
            return [chave.strip() for chave in bruto.split(",") if chave.strip()]
        if self._fernet_efemero is None:
            logger.warning("Usando FERNET_KEYS efêmera (permitido apenas em dev/test).")
            self._fernet_efemero = Fernet.generate_key().decode("utf-8")
        return [self._fernet_efemero]


@lru_cache
def obter_configuracoes() -> Configuracoes:
    """Instância cacheada de configurações da aplicação."""
    return Configuracoes()
