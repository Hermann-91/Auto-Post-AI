"""Testes unitários do EditorVideo (FFmpeg com executor injetado)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.midia.editor_video import (
    ConfiguracaoVideo,
    EditorVideo,
    ErroProcessamentoMidia,
)


def test_processar_video_sem_logo_monta_comando_9_16_com_audio() -> None:
    capturado: dict[str, object] = {}

    def fake_executor(cmd: list[str], timeout_segundos: float) -> subprocess.CompletedProcess[str]:
        capturado["cmd"] = cmd
        capturado["timeout"] = timeout_segundos
        capturado["entrada_existe"] = Path(cmd[cmd.index("-i") + 1]).exists()
        Path(cmd[-1]).write_bytes(b"mp4-processado")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    editor = EditorVideo(executor=fake_executor)
    saida = editor.processar_video(
        b"video-bruto",
        logo_bytes=None,
        config=ConfiguracaoVideo(proporcao="9:16", timeout_segundos=45.0),
    )

    assert saida == b"mp4-processado"
    assert capturado["entrada_existe"] is True
    assert capturado["timeout"] == 45.0
    cmd = capturado["cmd"]
    assert isinstance(cmd, list)
    assert "-map" in cmd and "0:a?" in cmd
    assert "aac" in cmd and "+faststart" in cmd
    assert any("scale=1080:1920:force_original_aspect_ratio=increase" in arg for arg in cmd)
    assert not Path(cmd[-1]).parent.exists()


def test_processar_video_com_logo_usa_filter_complex_4_5() -> None:
    cmd_capturado: list[str] = []

    def fake_executor(cmd: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        cmd_capturado.extend(cmd)
        Path(cmd[-1]).write_bytes(b"mp4-com-logo")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    editor = EditorVideo(executor=fake_executor)
    saida = editor.processar_video(
        b"video-bruto",
        logo_bytes=b"png-logo",
        config=ConfiguracaoVideo(proporcao="4:5"),
    )

    assert saida == b"mp4-com-logo"
    assert "-filter_complex" in cmd_capturado
    assert "[outv]" in cmd_capturado
    assert "0:a?" in cmd_capturado
    assert any("1080:1350" in arg for arg in cmd_capturado)


def test_processar_video_trata_falhas_e_validacoes() -> None:
    def executor_ausente(cmd: list[str], _t: float) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("ffmpeg not found")

    with pytest.raises(ErroProcessamentoMidia, match="não encontrado"):
        EditorVideo(executor=executor_ausente).processar_video(b"video")

    def executor_timeout(cmd: list[str], t: float) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd, t)

    with pytest.raises(ErroProcessamentoMidia, match="excedeu o limite"):
        EditorVideo(executor=executor_timeout).processar_video(b"video")

    def executor_erro(cmd: list[str], _t: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, "", "erro codec")

    with pytest.raises(ErroProcessamentoMidia, match="erro codec"):
        EditorVideo(executor=executor_erro).processar_video(b"video")

    with pytest.raises(ErroValidacaoDominio, match="vazio"):
        EditorVideo(executor=executor_erro).processar_video(b"")
