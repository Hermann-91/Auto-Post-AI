"""Testes unitários do ProcessadorImagem (Pillow em memória)."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.midia.processador_imagem import ProcessadorImagem, converter_para_rgb


def _gerar_imagem_bytes(
    largura: int,
    altura: int,
    formato: str = "JPEG",
    modo: str = "RGB",
    cor: tuple[int, ...] = (40, 120, 200),
) -> bytes:
    img = Image.new(modo, (largura, altura), cor)
    buf = BytesIO()
    img.save(buf, format=formato)
    return buf.getvalue()


def test_compactar_entrada_reduz_dimensao_e_remove_exif() -> None:
    img = Image.new("RGB", (4000, 3000), (20, 140, 60))
    exif = Image.Exif()
    exif[274] = 1
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())

    compactada = ProcessadorImagem.compactar_entrada(buf.getvalue(), max_lado=2048, qualidade=85)
    with Image.open(BytesIO(compactada)) as saida:
        assert saida.format == "JPEG"
        assert max(saida.size) == 2048
        assert saida.size == (2048, 1536)
        assert "exif" not in saida.info


def test_otimizar_para_formato_corrige_orientacao_exif() -> None:
    # Imagem 800x400: metade esquerda vermelha, metade direita azul; EXIF 6 gira 90° CW -> 400x800
    img = Image.new("RGB", (800, 400), (255, 0, 0))
    direita = Image.new("RGB", (400, 400), (0, 0, 255))
    img.paste(direita, (400, 0))
    exif = Image.Exif()
    exif[274] = 6
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())

    processada = ProcessadorImagem.otimizar_para_formato(
        buf.getvalue(),
        proporcao="4:5",
        fator_contraste=1.0,
        fator_cor=1.0,
    )
    with Image.open(BytesIO(processada)) as saida:
        assert saida.size == (1080, 1350)
        pixel_topo = saida.getpixel((540, 50))
        pixel_base = saida.getpixel((540, 1300))
        assert isinstance(pixel_topo, tuple) and isinstance(pixel_base, tuple)
        assert pixel_topo[0] > 200 and pixel_topo[2] < 50
        assert pixel_base[2] > 200 and pixel_base[0] < 50


@pytest.mark.parametrize(
    ("proporcao", "esperado"),
    [("4:5", (1080, 1350)), ("9:16", (1080, 1920)), ("1:1", (1080, 1080))],
)
def test_otimizar_para_formato_respeita_proporcoes(
    proporcao: str,
    esperado: tuple[int, int],
) -> None:
    entrada = _gerar_imagem_bytes(1600, 900)
    saida_bytes = ProcessadorImagem.otimizar_para_formato(entrada, proporcao=proporcao)
    with Image.open(BytesIO(saida_bytes)) as saida:
        assert saida.mode == "RGB"
        assert saida.size == esperado


def test_converter_para_rgb_compoe_transparencia_sobre_fundo_branco() -> None:
    png_rgba = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    rgb = converter_para_rgb(png_rgba)
    assert rgb.mode == "RGB"
    assert rgb.getpixel((50, 50)) == (255, 255, 255)


def test_erros_validacao_processador_imagem() -> None:
    with pytest.raises(ErroValidacaoDominio, match="vazio"):
        ProcessadorImagem.compactar_entrada(b"")

    with pytest.raises(ErroValidacaoDominio, match="inválida"):
        ProcessadorImagem.otimizar_para_formato(b"nao-e-uma-imagem")

    entrada = _gerar_imagem_bytes(400, 400)
    with pytest.raises(ErroValidacaoDominio, match="Proporção"):
        ProcessadorImagem.otimizar_para_formato(entrada, proporcao="16:9")
