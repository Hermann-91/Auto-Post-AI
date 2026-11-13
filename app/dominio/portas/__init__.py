"""Portas e estratégias (Ports & Adapters) da camada de domínio."""

from app.dominio.portas.ia_meta import (
    ClienteIAPort,
    PesquisaTendenciasPort,
    ProvedorAuthMetaPort,
    PublicadorMidiaStrategyPort,
)
from app.dominio.portas.midia_storage import (
    DriveImportPort,
    MidiaStrategyPort,
    StorageMidiaPort,
)
from app.dominio.portas.repositorios_conteudo import (
    ConfigIARepositoryPort,
    CustoRepositoryPort,
    MidiaRepositoryPort,
    PlanejamentoRepositoryPort,
    PostagemRepositoryPort,
    RagRepositoryPort,
)
from app.dominio.portas.repositorios_tenant import (
    ContaIGRepositoryPort,
    EmpresaRepositoryPort,
    RefreshTokenRepositoryPort,
    UsuarioRepositoryPort,
)
from app.dominio.portas.seguranca import (
    CaptchaPort,
    CriptografiaPort,
    HasherSenhaPort,
    PayloadAccessToken,
    RateLimiterPort,
    TokenJwtPort,
)

__all__ = [
    "CaptchaPort",
    "ClienteIAPort",
    "ConfigIARepositoryPort",
    "ContaIGRepositoryPort",
    "CriptografiaPort",
    "CustoRepositoryPort",
    "DriveImportPort",
    "EmpresaRepositoryPort",
    "HasherSenhaPort",
    "MidiaRepositoryPort",
    "MidiaStrategyPort",
    "PayloadAccessToken",
    "PesquisaTendenciasPort",
    "PlanejamentoRepositoryPort",
    "PostagemRepositoryPort",
    "ProvedorAuthMetaPort",
    "PublicadorMidiaStrategyPort",
    "RagRepositoryPort",
    "RateLimiterPort",
    "RefreshTokenRepositoryPort",
    "StorageMidiaPort",
    "TokenJwtPort",
    "UsuarioRepositoryPort",
]
