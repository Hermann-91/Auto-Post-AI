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
    cookie_csrf_nome: str = "csrf_token"
    rate_limit_max_tentativas: int = Field(default=5, ge=1)
    rate_limit_janela_segundos: int = Field(default=900, ge=10)
    redis_url: str | None = None

    # Cloudflare Turnstile
    captcha_enabled: bool = False
    turnstile_site_key: str = ""
    turnstile_secret_key: SecretStr | None = None
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    turnstile_timeout_segundos: float = Field(default=5.0, ge=1.0, le=30.0)

    # Banco de Dados (SQLAlchemy Async + Alembic)
    database_url: SecretStr | None = None
    db_echo: bool = False
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=100)

    # Storage em Nuvem (Cloudflare R2 / S3) e Local (dev/test)
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: str = "./data/storage"
    storage_local_base_url: str = "http://localhost:8000/media"
    storage_bucket: str | None = None
    storage_endpoint_url: str | None = None
    storage_region: str = "auto"
    storage_access_key_id: SecretStr | None = None
    storage_secret_access_key: SecretStr | None = None
    storage_public_base_url: str | None = None
    storage_presigned_ttl_segundos: int = Field(default=3600, ge=60, le=604800)

    # Cotas de Mídia da Biblioteca
    cota_max_itens: int = Field(default=250, ge=1)
    cota_max_bytes: int = Field(default=1073741824, ge=1048576)

    # OpenRouter (Texto, Visão e Nano Banana) & Tendências Web
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_segundos: float = Field(default=60.0, ge=5.0, le=300.0)
    openrouter_site_url: str | None = None
    openrouter_app_title: str = "Robo-Auto-Inst"
    openrouter_modelo_texto_padrao: str = "deepseek/deepseek-v4-flash"
    openrouter_modelo_texto_fallback: str = "openrouter/free"
    openrouter_modelo_visao_padrao: str = "google/gemini-2.5-flash-lite"
    openrouter_modelo_img_padrao: str = "google/gemini-3.1-flash-image"
    tendencias_cache_ttl_horas: int = Field(default=48, ge=24, le=72)
    tendencias_busca_url: str = "https://api.duckduckgo.com/"
    tendencias_timeout_segundos: float = Field(default=10.0, ge=1.0, le=30.0)

    # Meta Graph API (Instagram Login V1) & Worker de Agendamento
    meta_app_id: str | None = None
    meta_app_secret: SecretStr | None = None
    meta_redirect_uri: str | None = None
    meta_oauth_authorize_url: str = "https://www.instagram.com/oauth/authorize"
    meta_oauth_token_url: str = "https://api.instagram.com/oauth/access_token"
    meta_graph_base_url: str = "https://graph.instagram.com"
    meta_graph_version: str = "v22.0"
    meta_timeout_segundos: float = Field(default=30.0, ge=5.0, le=120.0)
    meta_polling_intervalos_segundos: list[float] = Field(
        default_factory=lambda: [3.0, 5.0, 10.0, 15.0, 15.0]
    )
    worker_poll_segundos: float = Field(default=15.0, ge=1.0, le=300.0)
    worker_lock_ttl_segundos: int = Field(default=300, ge=30, le=3600)
    worker_renovar_token_dias_antes: int = Field(default=10, ge=1, le=30)
    worker_concorrencia_max: int = Field(default=3, ge=1, le=20)

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
            if self.database_url is None or not self.database_url.get_secret_value().strip():
                raise ValueError("DATABASE_URL é obrigatória em produção.")
            if (
                self.storage_backend == "local"
                and not self.storage_local_base_url.startswith("https://")
            ):
                raise ValueError(
                    "STORAGE_LOCAL_BASE_URL deve usar HTTPS com STORAGE_BACKEND='local'."
                )
            if self.meta_redirect_uri and not self.meta_redirect_uri.startswith("https://"):
                raise ValueError("META_REDIRECT_URI deve usar HTTPS em produção.")
        if self.storage_backend == "s3":
            if not self.storage_bucket or not self.storage_bucket.strip():
                raise ValueError("STORAGE_BUCKET é obrigatório com STORAGE_BACKEND='s3'.")
            if self.storage_access_key_id is None or self.storage_secret_access_key is None:
                raise ValueError("Credenciais S3/R2 são obrigatórias com STORAGE_BACKEND='s3'.")
        return self

    def resolver_database_url(self) -> str:
        """Retorna DATABASE_URL configurada ou fallback SQLite apenas fora de produção."""
        if self.database_url is not None and self.database_url.get_secret_value().strip():
            return self.database_url.get_secret_value().strip()
        if self.app_env == "prod":
            raise ValueError("DATABASE_URL é obrigatória em produção.")
        return "sqlite+aiosqlite:///./robo_auto_inst_dev.db"

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
