"""Container de injeção de dependências para IA, RAG, criação e planejamento."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from app.api.dependencias.container_auth import ContainerAuth
from app.core.config import Configuracoes
from app.dominio.portas.ia_meta import ClienteIAPort, ClienteVisaoPort, PesquisaTendenciasPort
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import (
    ConfigIARepositoryPort,
    CustoRepositoryPort,
    MidiaRepositoryPort,
    PlanejamentoRepositoryPort,
    PostagemRepositoryPort,
    RagRepositoryPort,
)
from app.dominio.portas.repositorios_tenant import ContaIGRepositoryPort, EmpresaRepositoryPort
from app.infra.db.repo_conta_ig_sql import SqlContaIGRepository
from app.infra.db.repo_ia_rag_sql import (
    SqlConfigIARepository,
    SqlPlanejamentoRepository,
    SqlRagRepository,
)
from app.infra.db.repo_midia_sql import SqlMidiaRepository
from app.infra.db.repo_post_custo_sql import SqlCustoRepository, SqlPostagemRepository
from app.infra.db.sessao import criar_session_factory
from app.infra.ia import (
    BuscadorTendenciasDuckDuckGo,
    CacheTendenciasMemoria,
    CacheTendenciasRedis,
    ClienteIANaoConfigurado,
    ClienteOpenRouter,
    PesquisaTendenciasAdapter,
)
from app.infra.ia.pesquisa_tendencias import CacheTendenciasPort, ClienteRedisCachePort
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryConfigIARepository,
    InMemoryContaIGRepository,
    InMemoryMidiaRepository,
    InMemoryRagRepository,
)
from app.infra.memoria.repo_publicacao_mem import (
    InMemoryCustoRepository,
    InMemoryPlanejamentoRepository,
    InMemoryPostagemRepository,
)
from app.infra.midia.estrategias_midia import FabricaEstrategiasMidia
from app.infra.storage import criar_storage_adapter


@dataclass(slots=True)
class ContainerIA:
    """Agrupa repositórios, gateway OpenRouter, storage e pipeline de mídia."""

    config: Configuracoes
    empresa_repo: EmpresaRepositoryPort
    conta_repo: ContaIGRepositoryPort
    config_ia_repo: ConfigIARepositoryPort
    rag_repo: RagRepositoryPort
    midia_repo: MidiaRepositoryPort
    plano_repo: PlanejamentoRepositoryPort
    post_repo: PostagemRepositoryPort
    custo_repo: CustoRepositoryPort
    storage: StorageMidiaPort
    cliente_ia: ClienteIAPort
    cliente_visao: ClienteVisaoPort
    tendencias: PesquisaTendenciasPort
    pipeline_midia: FabricaEstrategiasMidia


def _montar_cliente_openrouter(cfg: Configuracoes) -> tuple[ClienteIAPort, ClienteVisaoPort]:
    chave = (
        cfg.openrouter_api_key.get_secret_value().strip()
        if cfg.openrouter_api_key is not None
        else ""
    )
    if not chave:
        stub = ClienteIANaoConfigurado()
        return stub, stub
    cliente = ClienteOpenRouter(
        api_key=chave,
        base_url=cfg.openrouter_base_url,
        timeout_segundos=cfg.openrouter_timeout_segundos,
        site_url=cfg.openrouter_site_url,
        app_title=cfg.openrouter_app_title,
        modelo_fallback_free=cfg.openrouter_modelo_texto_fallback,
    )
    return cliente, cliente


def construir_container_ia(config: Configuracoes, auth: ContainerAuth) -> ContainerIA:
    """Monta adaptadores SQL/Memória, Redis/Memória e cliente OpenRouter."""
    conta_repo: ContaIGRepositoryPort
    config_ia_repo: ConfigIARepositoryPort
    rag_repo: RagRepositoryPort
    midia_repo: MidiaRepositoryPort
    plano_repo: PlanejamentoRepositoryPort
    post_repo: PostagemRepositoryPort
    custo_repo: CustoRepositoryPort

    if auth.db_engine is not None:
        sf = criar_session_factory(auth.db_engine)
        conta_repo, config_ia_repo = SqlContaIGRepository(sf), SqlConfigIARepository(sf)
        rag_repo, midia_repo = SqlRagRepository(sf), SqlMidiaRepository(sf)
        plano_repo, post_repo = SqlPlanejamentoRepository(sf), SqlPostagemRepository(sf)
        custo_repo = SqlCustoRepository(sf)
    else:
        conta_repo, config_ia_repo = InMemoryContaIGRepository(), InMemoryConfigIARepository()
        rag_repo, midia_repo = InMemoryRagRepository(), InMemoryMidiaRepository()
        plano_repo = InMemoryPlanejamentoRepository()
        post_repo, custo_repo = InMemoryPostagemRepository(), InMemoryCustoRepository()

    cliente_ia, cliente_visao = _montar_cliente_openrouter(config)
    cache_tend: CacheTendenciasPort = (
        CacheTendenciasRedis(cast(ClienteRedisCachePort, auth.redis_client))
        if auth.redis_client is not None
        else CacheTendenciasMemoria()
    )
    buscador = BuscadorTendenciasDuckDuckGo(
        base_url=config.tendencias_busca_url,
        timeout_segundos=config.tendencias_timeout_segundos,
    )
    return ContainerIA(
        config=config,
        empresa_repo=auth.empresa_repo,
        conta_repo=conta_repo,
        config_ia_repo=config_ia_repo,
        rag_repo=rag_repo,
        midia_repo=midia_repo,
        plano_repo=plano_repo,
        post_repo=post_repo,
        custo_repo=custo_repo,
        storage=criar_storage_adapter(config),
        cliente_ia=cliente_ia,
        cliente_visao=cliente_visao,
        tendencias=PesquisaTendenciasAdapter(cache=cache_tend, buscador=buscador),
        pipeline_midia=FabricaEstrategiasMidia(),
    )
