"""Adaptadores de infraestrutura para OpenRouter, RAG e pesquisa web."""

from app.infra.ia.buscador_web_real import BuscadorWebReal
from app.infra.ia.cliente_openrouter import (
    ClienteIANaoConfigurado,
    ClienteOpenRouter,
)
from app.infra.ia.extrator_rag import ExtratorConteudoRag
from app.infra.ia.pesquisa_tendencias import (
    CacheTendenciasMemoria,
    CacheTendenciasRedis,
    PesquisaTendenciasAdapter,
)

__all__ = [
    "BuscadorWebReal",
    "CacheTendenciasMemoria",
    "CacheTendenciasRedis",
    "ClienteIANaoConfigurado",
    "ClienteOpenRouter",
    "ExtratorConteudoRag",
    "PesquisaTendenciasAdapter",
]
