"""Adaptadores oficiais da Meta Graph API (Instagram Login e publicação)."""

from app.infra.meta.auth_instagram_login import (
    AuthInstagramLoginAdapter,
    AuthMetaNaoConfigurado,
)
from app.infra.meta.cliente_meta_http import ClienteMetaHttp
from app.infra.meta.estrategias_publicacao import (
    CarrosselPublicacaoStrategy,
    FabricaPublicadoresMeta,
    FotoPublicacaoStrategy,
    ReelsPublicacaoStrategy,
    StoriesPublicacaoStrategy,
)
from app.infra.meta.modelos_meta import LimitePublicacaoMeta, StatusContainerMeta

__all__ = [
    "AuthInstagramLoginAdapter",
    "AuthMetaNaoConfigurado",
    "CarrosselPublicacaoStrategy",
    "ClienteMetaHttp",
    "FabricaPublicadoresMeta",
    "FotoPublicacaoStrategy",
    "LimitePublicacaoMeta",
    "ReelsPublicacaoStrategy",
    "StatusContainerMeta",
    "StoriesPublicacaoStrategy",
]
