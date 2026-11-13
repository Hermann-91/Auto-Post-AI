"""Testes unitários do GeradorCarrossel."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.midia.gerador_carrossel import ConfiguracaoCarrossel, GeradorCarrossel


def _foto_bytes(cor: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (1080, 1350), cor)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _logo_bytes() -> bytes:
    img = Image.new("RGBA", (300, 150), (240, 200, 80, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_gerar_slides_sem_logo_e_sem_encerramento() -> None:
    gerador = GeradorCarrossel()
    fotos = [_foto_bytes((200, 50, 50)), _foto_bytes((50, 200, 50)), _foto_bytes((50, 50, 200))]

    slides = gerador.gerar_slides(fotos)
    assert len(slides) == 3
    for slide in slides:
        with Image.open(BytesIO(slide)) as img:
            assert img.format == "JPEG"
            assert img.size == (1080, 1350)


def test_gerar_slides_com_logo_e_slide_encerramento() -> None:
    gerador = GeradorCarrossel()
    fotos = [_foto_bytes((100, 100, 100)), _foto_bytes((150, 150, 150))]
    cfg = ConfiguracaoCarrossel(
        incluir_slide_encerramento=True,
        cor_fundo_encerramento=(10, 20, 30),
    )

    slides = gerador.gerar_slides(fotos, logo_bytes=_logo_bytes(), config=cfg)
    assert len(slides) == 3
    with Image.open(BytesIO(slides[-1])) as encerramento:
        assert encerramento.size == (1080, 1350)
        pixel_fundo = encerramento.getpixel((20, 675))
        assert isinstance(pixel_fundo, tuple)
        assert pixel_fundo[2] < 60


def test_gerar_slides_rejeita_invariantes_meta() -> None:
    gerador = GeradorCarrossel()

    with pytest.raises(ErroValidacaoDominio, match="pelo menos"):
        gerador.gerar_slides([])

    with pytest.raises(ErroValidacaoDominio, match="entre 2 e 10"):
        gerador.gerar_slides([_foto_bytes((1, 2, 3))])

    muitas = [_foto_bytes((i, i, i)) for i in range(11)]
    with pytest.raises(ErroValidacaoDominio, match="entre 2 e 10"):
        gerador.gerar_slides(muitas)

    with pytest.raises(ErroValidacaoDominio, match="logotipo"):
        gerador.gerar_slides(
            [_foto_bytes((1, 2, 3)), _foto_bytes((4, 5, 6))],
            logo_bytes=None,
            config=ConfiguracaoCarrossel(incluir_slide_encerramento=True),
        )
