"""Testes dos modelos, parser de erros e validadores Meta em modelos_meta.py."""

from __future__ import annotations

import httpx
import pytest

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.meta.modelos_meta import (
    LimitePublicacaoMeta,
    eh_video_midia,
    extrair_erro_meta,
    validar_urls_publicas,
)


def test_modelos_e_validadores_meta() -> None:
    assert LimitePublicacaoMeta(50, 50).atingido is True
    assert LimitePublicacaoMeta(5, 50).atingido is False
    assert eh_video_midia("conta/reels.MP4?sig=1") is True
    assert eh_video_midia("conta/foto.jpg") is False
    assert validar_urls_publicas(["https://cdn.site/a.jpg"], exigir_https=True) == [
        "https://cdn.site/a.jpg"
    ]
    with pytest.raises(ErroValidacaoDominio):
        validar_urls_publicas(["http://cdn.site/a.jpg"], exigir_https=True)

    resp = httpx.Response(400, json={"error": {"message": "Bad URL", "code": 9004}})
    assert extrair_erro_meta(resp) == "Bad URL (code=9004)"
