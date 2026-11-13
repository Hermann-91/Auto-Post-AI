"""Adaptadores de infraestrutura para OpenRouter e pesquisa de tendências."""

from app.infra.ia.cliente_openrouter import (
    ClienteIANaoConfigurado,
    ClienteOpenRouter,
)
from app.infra.ia.pesquisa_tendencias import (
    BuscadorTendenciasDuckDuckGo,
    CacheTendenciasMemoria,
    CacheTendenciasRedis,
    PesquisaTendenciasAdapter,
)

__all__ = [
    "BuscadorTendenciasDuckDuckGo",
    "CacheTendenciasMemoria",
    "CacheTendenciasRedis",
    "ClienteIANaoConfigurado",
    "ClienteOpenRouter",
    "PesquisaTendenciasAdapter",
]
