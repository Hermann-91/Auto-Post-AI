"""Testes unitários do CompositorCapa."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.midia.compositor_capa import CompositorCapa, ConfiguracaoCapa


def _bytes_imagem(
    largura: int,
    altura: int,
    formato: str,
    modo: str,
    cor: tuple[int, ...],
) -> bytes:
    img = Image.new(modo, (largura, altura), cor)
    buf = BytesIO()
    img.save(buf, format=formato)
    return buf.getvalue()


def test_compor_sem_logo_e_sem_gradiente_preserva_cor_e_dimensoes() -> None:
    foto = _bytes_imagem(1200, 1200, "JPEG", "RGB", (200, 180, 160))
    cfg = ConfiguracaoCapa(aplicar_gradiente=False)

    saida = CompositorCapa.compor(foto, logo_bytes=None, config=cfg, proporcao="4:5")
    with Image.open(BytesIO(saida)) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"
        assert img.size == (1080, 1350)


def test_compor_com_gradiente_e_logo_altera_topo_e_suporta_9_16() -> None:
    foto = _bytes_imagem(1080, 1920, "JPEG", "RGB", (230, 230, 230))
    logo = _bytes_imagem(200, 100, "PNG", "RGBA", (20, 220, 40, 255))
    cfg = ConfiguracaoCapa(aplicar_gradiente=True, opacidade_topo=200, margem_topo_logo=40)

    saida = CompositorCapa.compor(foto, logo_bytes=logo, config=cfg, proporcao="9:16")
    with Image.open(BytesIO(saida)) as img:
        assert img.size == (1080, 1920)
        pixel_logo = img.getpixel((540, 90))
        pixel_borda_topo = img.getpixel((10, 10))
        assert isinstance(pixel_logo, tuple) and isinstance(pixel_borda_topo, tuple)
        assert pixel_logo[1] > pixel_logo[0] + 100
        assert pixel_borda_topo[0] < 120


def test_configuracao_capa_valida_limites() -> None:
    with pytest.raises(ErroValidacaoDominio, match="sobrepor"):
        ConfiguracaoCapa(altura_gradiente_topo=0.6, altura_gradiente_base=0.5)

    with pytest.raises(ErroValidacaoDominio, match="Opacidade"):
        ConfiguracaoCapa(opacidade_topo=300)
