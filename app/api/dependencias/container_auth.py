"""Container de injeção de dependências da camada de autenticação."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Depends, Request
from redis.asyncio import Redis

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

    async def fechar(self) -> None:
        """Libera conexões externas (Redis) no encerramento da aplicação."""
        if self.redis_client is not None:
            await self.redis_client.aclose()


def construir_container_auth(config: Configuracoes) -> ContainerAuth:
    """Monta adaptadores concretos conforme ambiente (memória na Fase 1)."""
    captcha: CaptchaPort
    if config.captcha_enabled and config.turnstile_secret_key is not None:
        captcha = CloudflareTurnstileAdapter(
            secret_key=config.turnstile_secret_key.get_secret_value(),
            verify_url=config.turnstile_verify_url,
            timeout_segundos=config.turnstile_timeout_segundos,
        )
    else:
        captcha = StubCaptchaAdapter(sempre_valido=True)

    redis_client: Any = None
    rate_limiter: RateLimiterPort
    if config.redis_url:
        redis_client = Redis.from_url(config.redis_url, decode_responses=False)
        rate_limiter = RedisRateLimiter(
            redis_client=cast(ClienteRedisEvalPort, redis_client),
            max_tentativas=config.rate_limit_max_tentativas,
            janela_segundos=config.rate_limit_janela_segundos,
        )
    else:
        rate_limiter = InMemoryRateLimiter(
            max_tentativas=config.rate_limit_max_tentativas,
            janela_segundos=config.rate_limit_janela_segundos,
        )

    return ContainerAuth(
        config=config,
        empresa_repo=InMemoryEmpresaRepository(),
        usuario_repo=InMemoryUsuarioRepository(),
        refresh_repo=InMemoryRefreshTokenRepository(),
        hasher=Argon2idHasher(
            time_cost=config.argon2_time_cost,
            memory_cost=config.argon2_memory_cost_kib,
            parallelism=config.argon2_parallelism,
        ),
        tokens=JwtTokenService(
            chave_secreta=config.resolver_jwt_secret(),
            algoritmo=config.jwt_algoritmo,
            issuer=config.jwt_issuer,
            audience=config.jwt_audience,
            access_minutos=config.access_token_minutos,
        ),
        captcha=captcha,
        rate_limiter=rate_limiter,
        redis_client=redis_client,
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
