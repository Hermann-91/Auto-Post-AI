"""Testes de integração HTTP da rota pública assinada /media/{chave}."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from httpx import ASGITransport, AsyncClient

from app.core.config import Configuracoes
from app.main import criar_app


async def test_media_publica_valida_assinatura_hmac(tmp_path: Path) -> None:
    cfg = Configuracoes(
        app_env="test",
        storage_local_dir=str(tmp_path / "media"),
        storage_local_base_url="https://testserver/media",
    )
    app = criar_app(cfg)
    chave = "emp1/ig1/processadas/post.jpg"
    url = await app.state.ia_container.storage.enviar_bytes(chave, b"\xff\xd8\xffok", "image/jpeg")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as cli:
        ok = await cli.get(f"{parsed.path}?exp={qs['exp'][0]}&sig={qs['sig'][0]}")
        assert ok.status_code == 200
        assert ok.content == b"\xff\xd8\xffok"
        assert ok.headers["x-content-type-options"] == "nosniff"
        assert ok.headers["content-disposition"] == "inline"
        assert "max-age=31536000" in ok.headers["strict-transport-security"]

        sem_sig = await cli.get(parsed.path)
        assert sem_sig.status_code == 403

        sig_falsa = await cli.get(f"{parsed.path}?exp={qs['exp'][0]}&sig=invalida")
        assert sig_falsa.status_code == 403

        expirada = await cli.get(f"{parsed.path}?exp=1&sig={qs['sig'][0]}")
        assert expirada.status_code == 403
