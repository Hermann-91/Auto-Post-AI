"""Container de injeção de dependências da camada de autenticação."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.aplicacao.auth import (
    AutenticarUsuarioUseCase,
    EncerrarSessaoUseCase,
    RegistrarUsuarioUseCase,
    RenovarSessaoUseCase,
)
from app.aplicacao.auth.emissao_sessao import EmissorSessaoAuth
from app.aplicacao.auth.protecao_entrada import GuardiaoEntradaAuth
from app.core.config import Configuracoes
from app.core.seguranca import Argon2idHasher, JwtTokenService
from app.dominio.portas.repositorios_tenant import (
    EmpresaRepositoryPort,
    RefreshTokenRepositoryPort,
    UsuarioRepositoryPort,
)
from app.dominio.portas.seguranca import (
    CaptchaPort,
    HasherSenhaPort,
    RateLimiterPort,
    TokenJwtPort,
)
from app.infra.db.repo_tenant_sql import (
    SqlEmpresaRepository,
    SqlRefreshTokenRepository,
    SqlUsuarioRepository,
)
from app.infra.db.sessao import criar_engine_async, criar_session_factory
from app.infra.memoria import (
    InMemoryEmpresaRepository,
    InMemoryRefreshTokenRepository,
    InMemoryUsuarioRepository,
)
from app.infra.seguranca import (
    CloudflareTurnstileAdapter,
    InMemoryRateLimiter,
    RedisRateLimiter,
    StubCaptchaAdapter,
)
from app.infra.seguranca.rate_limiter_redis import ClienteRedisEvalPort


@dataclass(slots=True)
class ContainerAuth:
    """Agrupa dependências e adaptadores do fluxo de autenticação por instância."""

    config: Configuracoes
    empresa_repo: EmpresaRepositoryPort
    usuario_repo: UsuarioRepositoryPort
    refresh_repo: RefreshTokenRepositoryPort
    hasher: HasherSenhaPort
    tokens: TokenJwtPort
    captcha: CaptchaPort
    rate_limiter: RateLimiterPort
    redis_client: Any = None
    db_engine: AsyncEngine | None = None

    async def fechar(self) -> None:
        """Libera conexões externas (Redis e pool SQL) no encerramento da aplicação."""
        if self.redis_client is not None:
            await self.redis_client.aclose()
        if self.db_engine is not None:
            await self.db_engine.dispose()


def construir_container_auth(config: Configuracoes) -> ContainerAuth:
    """Monta adaptadores concretos (SQLAlchemy + Redis em prod ou quando configurados)."""
    captcha: CaptchaPort
    if config.captcha_enabled and config.turnstile_secret_key is not None:
        captcha = CloudflareTurnstileAdapter(
            config.turnstile_secret_key.get_secret_value(), config.turnstile_verify_url,
            config.turnstile_timeout_segundos,
        )
    else:
        captcha = StubCaptchaAdapter(sempre_valido=True)

    redis_client: Any = None
    if config.redis_url:
        redis_client = Redis.from_url(config.redis_url, decode_responses=False)
        rate_limiter: RateLimiterPort = RedisRateLimiter(
            cast(ClienteRedisEvalPort, redis_client), config.rate_limit_max_tentativas,
            config.rate_limit_janela_segundos,
        )
    else:
        rate_limiter = InMemoryRateLimiter(
            config.rate_limit_max_tentativas, config.rate_limit_janela_segundos
        )

    db_engine: AsyncEngine | None = None
    if config.database_url is not None or config.app_env == "prod":
        db_engine = criar_engine_async(config)
        sf = criar_session_factory(db_engine)
        empresa_repo: EmpresaRepositoryPort = SqlEmpresaRepository(sf)
        usuario_repo: UsuarioRepositoryPort = SqlUsuarioRepository(sf)
        refresh_repo: RefreshTokenRepositoryPort = SqlRefreshTokenRepository(sf)
    else:
        empresa_repo = InMemoryEmpresaRepository()
        usuario_repo = InMemoryUsuarioRepository()
        refresh_repo = InMemoryRefreshTokenRepository()

    return ContainerAuth(
        config=config,
        empresa_repo=empresa_repo,
        usuario_repo=usuario_repo,
        refresh_repo=refresh_repo,
        hasher=Argon2idHasher(
            config.argon2_time_cost, config.argon2_memory_cost_kib, config.argon2_parallelism
        ),
        tokens=JwtTokenService(
            config.resolver_jwt_secret(), config.jwt_algoritmo, config.jwt_issuer,
            config.jwt_audience, config.access_token_minutos,
        ),
        captcha=captcha,
        rate_limiter=rate_limiter,
        redis_client=redis_client,
        db_engine=db_engine,
    )


def obter_container_auth(request: Request) -> ContainerAuth:
    """Recupera o container associado à instância da aplicação FastAPI."""
    return cast(ContainerAuth, request.app.state.auth_container)


def obter_config_app(
    container: Annotated[ContainerAuth, Depends(obter_container_auth)],
) -> Configuracoes:
    """Expõe configurações da instância para rotas e middlewares."""
    return container.config


def _criar_guardiao(container: ContainerAuth) -> GuardiaoEntradaAuth:
    return GuardiaoEntradaAuth(
        rate_limiter=container.rate_limiter,
        captcha=container.captcha,
    )


def _criar_emissor(container: ContainerAuth) -> EmissorSessaoAuth:
    return EmissorSessaoAuth(
        tokens=container.tokens,
        refresh_repo=container.refresh_repo,
        refresh_dias=container.config.refresh_token_dias,
    )


def obter_registrar_uc(
    container: Annotated[ContainerAuth, Depends(obter_container_auth)],
) -> RegistrarUsuarioUseCase:
    return RegistrarUsuarioUseCase(
        empresa_repo=container.empresa_repo,
        usuario_repo=container.usuario_repo,
        hasher=container.hasher,
        guardiao=_criar_guardiao(container),
        emissor=_criar_emissor(container),
    )


def obter_autenticar_uc(
    container: Annotated[ContainerAuth, Depends(obter_container_auth)],
) -> AutenticarUsuarioUseCase:
    return AutenticarUsuarioUseCase(
        usuario_repo=container.usuario_repo,
        hasher=container.hasher,
        guardiao=_criar_guardiao(container),
        emissor=_criar_emissor(container),
    )


def obter_renovar_uc(
    container: Annotated[ContainerAuth, Depends(obter_container_auth)],
) -> RenovarSessaoUseCase:
    return RenovarSessaoUseCase(
        tokens=container.tokens,
        refresh_repo=container.refresh_repo,
        usuario_repo=container.usuario_repo,
        emissor=_criar_emissor(container),
    )


def obter_encerrar_uc(
    container: Annotated[ContainerAuth, Depends(obter_container_auth)],
) -> EncerrarSessaoUseCase:
    return EncerrarSessaoUseCase(
        tokens=container.tokens,
        refresh_repo=container.refresh_repo,
    )
