"""Container de injeção de dependências para Meta Graph API e Publicação."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from app.api.dependencias.container_auth import ContainerAuth
from app.api.dependencias.container_ia import ContainerIA
from app.aplicacao.publicacao.servico_agendamento import (
    LockPublicacaoPort,
    ServicoAgendamentoUseCase,
)
from app.aplicacao.publicacao.servico_oauth_meta import (
    ServicoOAuthMetaUseCase,
    StateOAuthStorePort,
)
from app.core.config import Configuracoes
from app.core.seguranca.criptografia_fernet import FernetCipher
from app.dominio.portas.ia_meta import ProvedorAuthMetaPort
from app.dominio.portas.seguranca import CriptografiaPort
from app.infra.meta.auth_instagram_login import (
    AuthInstagramLoginAdapter,
    AuthMetaNaoConfigurado,
)
from app.infra.meta.cliente_meta_http import ClienteMetaHttp
from app.infra.meta.estrategias_publicacao import FabricaPublicadoresMeta
from app.infra.meta.state_oauth_store import (
    ClienteRedisStatePort,
    StateOAuthMemoria,
    StateOAuthRedis,
)
from app.infra.seguranca.lock_distribuido import (
    ClienteRedisLockPort,
    LockMemoria,
    LockRedis,
)


@dataclass(slots=True)
class ContainerMeta:
    """Agrupa adaptadores Meta OAuth, HTTP, criptografia, state e locks."""

    config: Configuracoes
    cripto: CriptografiaPort
    auth_meta: ProvedorAuthMetaPort
    cliente_meta: ClienteMetaHttp
    fabrica_publicadores: FabricaPublicadoresMeta
    state_store: StateOAuthStorePort
    lock_distribuido: LockPublicacaoPort


def _montar_auth_meta(cfg: Configuracoes) -> ProvedorAuthMetaPort:
    app_id = (cfg.meta_app_id or "").strip()
    secret = cfg.meta_app_secret.get_secret_value().strip() if cfg.meta_app_secret else ""
    redirect = (cfg.meta_redirect_uri or "").strip()
    if not app_id or not secret or not redirect:
        return AuthMetaNaoConfigurado()
    return AuthInstagramLoginAdapter(
        app_id=app_id,
        app_secret=secret,
        redirect_uri=redirect,
        authorize_url=cfg.meta_oauth_authorize_url,
        token_url=cfg.meta_oauth_token_url,
        graph_base_url=cfg.meta_graph_base_url,
        graph_version=cfg.meta_graph_version,
        timeout_segundos=cfg.meta_timeout_segundos,
    )


def construir_container_meta(
    config: Configuracoes,
    auth: ContainerAuth,
    ia: ContainerIA,
) -> ContainerMeta:
    """Monta adaptadores Meta OAuth, Graph API e locks Redis/Memória."""
    _ = ia
    cliente_meta = ClienteMetaHttp(
        graph_base_url=config.meta_graph_base_url,
        graph_version=config.meta_graph_version,
        timeout_segundos=config.meta_timeout_segundos,
        polling_intervalos=config.meta_polling_intervalos_segundos,
    )
    state_store: StateOAuthStorePort = (
        StateOAuthRedis(cast(ClienteRedisStatePort, auth.redis_client))
        if auth.redis_client is not None
        else StateOAuthMemoria()
    )
    lock_distribuido: LockPublicacaoPort = (
        LockRedis(cast(ClienteRedisLockPort, auth.redis_client))
        if auth.redis_client is not None
        else LockMemoria()
    )
    return ContainerMeta(
        config=config,
        cripto=FernetCipher(config.resolver_fernet_keys()),
        auth_meta=_montar_auth_meta(config),
        cliente_meta=cliente_meta,
        fabrica_publicadores=FabricaPublicadoresMeta(
            cliente_meta, exigir_https=config.app_env == "prod"
        ),
        state_store=state_store,
        lock_distribuido=lock_distribuido,
    )


def criar_oauth_meta_uc(ia: ContainerIA, meta: ContainerMeta) -> ServicoOAuthMetaUseCase:
    return ServicoOAuthMetaUseCase(
        conta_repo=ia.conta_repo,
        auth_meta=meta.auth_meta,
        cripto=meta.cripto,
        state_store=meta.state_store,
    )


def criar_agendamento_uc(ia: ContainerIA, meta: ContainerMeta) -> ServicoAgendamentoUseCase:
    return ServicoAgendamentoUseCase(
        conta_repo=ia.conta_repo,
        midia_repo=ia.midia_repo,
        post_repo=ia.post_repo,
        storage=ia.storage,
        cripto=meta.cripto,
        fabrica_publicadores=meta.fabrica_publicadores,
        lock_distribuido=meta.lock_distribuido,
        lock_ttl_segundos=meta.config.worker_lock_ttl_segundos,
    )
