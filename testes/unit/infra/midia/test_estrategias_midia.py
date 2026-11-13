"""Testes unitários das estratégias multi-formato via Strategy + DI."""

from __future__ import annotations

import subprocess
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoMidia
from app.infra.midia.editor_video import EditorVideo
from app.infra.midia.estrategias_midia import FabricaEstrategiasMidia


def _jpeg_bytes(cor: tuple[int, int, int] = (90, 130, 170)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1200, 1200), cor).save(buf, format="JPEG")
    return buf.getvalue()


def _logo_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (200, 100), (255, 255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _editor_video_fake() -> EditorVideo:
    def executor(cmd: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        Path(cmd[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42-saida")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return EditorVideo(executor=executor)


async def test_estrategia_image_com_e_sem_logo() -> None:
    fabrica = FabricaEstrategiasMidia(editor_video=_editor_video_fake())
    foto = _jpeg_bytes()

    sem_logo = await fabrica.processar(TipoMidia.IMAGE, [foto], {"aplicar_logo": False})
    assert len(sem_logo) == 1
    with Image.open(BytesIO(sem_logo[0])) as img:
        assert img.size == (1080, 1350)

    com_logo = await fabrica.processar(
        TipoMidia.IMAGE,
        [foto],
        {"logo_bytes": _logo_bytes(), "proporcao": "1:1"},
    )
    with Image.open(BytesIO(com_logo[0])) as img:
        assert img.size == (1080, 1080)

    with pytest.raises(ErroValidacaoDominio, match="não permitida"):
        await fabrica.processar(TipoMidia.IMAGE, [foto], {"proporcao": "9:16"})


async def test_estrategia_carousel() -> None:
    fabrica = FabricaEstrategiasMidia(editor_video=_editor_video_fake())
    slides = await fabrica.processar(
        TipoMidia.CAROUSEL,
        [_jpeg_bytes((10, 20, 30)), _jpeg_bytes((40, 50, 60))],
        {"logo_bytes": _logo_bytes(), "incluir_slide_encerramento": True},
    )
    assert len(slides) == 3


async def test_estrategia_reels_exige_9_16_e_um_arquivo() -> None:
    fabrica = FabricaEstrategiasMidia(editor_video=_editor_video_fake())
    saida = await fabrica.processar(TipoMidia.REELS, [b"\x00\x00\x00\x18ftypmp42"], {})
    assert len(saida) == 1
    assert b"ftypmp42-saida" in saida[0]

    with pytest.raises(ErroValidacaoDominio, match="não permitida"):
        await fabrica.processar(TipoMidia.REELS, [b"video"], {"proporcao": "4:5"})

    with pytest.raises(ErroValidacaoDominio, match="exatamente 1"):
        await fabrica.processar(TipoMidia.REELS, [b"v1", b"v2"], {})


async def test_estrategia_stories_suporta_imagem_e_video_9_16() -> None:
    fabrica = FabricaEstrategiasMidia(editor_video=_editor_video_fake())

    story_img = await fabrica.processar(TipoMidia.STORIES, [_jpeg_bytes()], {})
    with Image.open(BytesIO(story_img[0])) as img:
        assert img.size == (1080, 1920)

    story_vid = await fabrica.processar(
        TipoMidia.STORIES,
        [b"\x00\x00\x00\x18ftypisom-dados-video"],
        {},
    )
    assert story_vid == [b"\x00\x00\x00\x18ftypmp42-saida"]

    with pytest.raises(ErroValidacaoDominio, match="não permitida"):
        await fabrica.processar(TipoMidia.STORIES, [_jpeg_bytes()], {"proporcao": "4:5"})
