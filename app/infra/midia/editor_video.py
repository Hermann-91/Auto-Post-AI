"""Editor determinístico de vídeos via FFmpeg com timeout e preservação de áudio."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.dominio.excecoes import ErroDominio, ErroValidacaoDominio

DIMENSOES_VIDEO: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
}


class ErroProcessamentoMidia(ErroDominio):
    """Falha operacional na execução do pipeline de mídia (ex.: FFmpeg)."""


class ExecutorComandoPort(Protocol):
    """Porta injetável para execução de comandos externos com timeout."""

    def __call__(
        self,
        cmd: list[str],
        timeout_segundos: float,
        /,
    ) -> subprocess.CompletedProcess[str]: ...


def _executar_subprocesso_padrao(
    cmd: list[str],
    timeout_segundos: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_segundos,
        check=False,
    )


@dataclass(frozen=True, slots=True)
class ConfiguracaoVideo:
    """Parâmetros de codificação MP4 compatíveis com a Meta Graph API."""

    proporcao: str = "9:16"
    inicio_fade_logo: float = 1.0
    duracao_fade_logo: float = 1.5
    largura_logo: int = 420
    margem_topo_logo: int = 70
    crf: int = 20
    preset: str = "medium"
    bitrate_audio: str = "128k"
    timeout_segundos: float = 120.0

    def __post_init__(self) -> None:
        if self.proporcao not in DIMENSOES_VIDEO:
            suportadas = ", ".join(sorted(DIMENSOES_VIDEO))
            raise ErroValidacaoDominio(
                f"Proporção de vídeo '{self.proporcao}' inválida. Use: {suportadas}."
            )
        if self.timeout_segundos <= 0:
            raise ErroValidacaoDominio("Timeout de vídeo deve ser maior que zero.")
        if self.largura_logo <= 0:
            raise ErroValidacaoDominio("Largura da logo deve ser maior que zero.")


class EditorVideo:
    """Processa vídeos MP4 H.264+AAC em memória via diretório temporário efêmero."""

    def __init__(
        self,
        binario_ffmpeg: str = "ffmpeg",
        executor: ExecutorComandoPort | None = None,
    ) -> None:
        self._binario_ffmpeg = binario_ffmpeg
        self._executor = executor or _executar_subprocesso_padrao

    def _montar_comando(
        self,
        entrada: Path,
        saida: Path,
        logo: Path | None,
        config: ConfiguracaoVideo,
    ) -> list[str]:
        largura, altura = DIMENSOES_VIDEO[config.proporcao]
        filtro_base = (
            f"scale={largura}:{altura}:force_original_aspect_ratio=increase,"
            f"crop={largura}:{altura},setsar=1"
        )
        cmd = [self._binario_ffmpeg, "-y", "-i", str(entrada)]
        if logo is not None:
            filtro_complexo = (
                f"[0:v]{filtro_base}[bg];"
                f"[1:v]scale={config.largura_logo}:-1,format=rgba,"
                f"fade=t=in:st={config.inicio_fade_logo}:"
                f"d={config.duracao_fade_logo}:alpha=1[logo];"
                f"[bg][logo]overlay=(main_w-overlay_w)/2:{config.margem_topo_logo}[outv]"
            )
            cmd.extend(["-i", str(logo), "-filter_complex", filtro_complexo, "-map", "[outv]"])
        else:
            cmd.extend(["-vf", filtro_base, "-map", "0:v:0"])

        cmd.extend(
            [
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-crf",
                str(config.crf),
                "-preset",
                config.preset,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                config.bitrate_audio,
                "-movflags",
                "+faststart",
                str(saida),
            ]
        )
        return cmd

    def processar_video(
        self,
        video_bytes: bytes,
        logo_bytes: bytes | None = None,
        config: ConfiguracaoVideo | None = None,
    ) -> bytes:
        """Padroniza proporção, áudio AAC e logo opcional, retornando bytes MP4."""
        if not video_bytes:
            raise ErroValidacaoDominio("Arquivo de vídeo vazio não pode ser processado.")
        if logo_bytes is not None and not logo_bytes:
            raise ErroValidacaoDominio("Logotipo em bytes não pode ser vazio.")

        cfg = config or ConfiguracaoVideo()
        with tempfile.TemporaryDirectory(prefix="robo_midia_") as dir_temp:
            raiz = Path(dir_temp)
            caminho_entrada = raiz / "entrada.mp4"
            caminho_saida = raiz / "saida.mp4"
            caminho_entrada.write_bytes(video_bytes)

            caminho_logo: Path | None = None
            if logo_bytes is not None:
                caminho_logo = raiz / "logo.png"
                caminho_logo.write_bytes(logo_bytes)

            cmd = self._montar_comando(caminho_entrada, caminho_saida, caminho_logo, cfg)
            try:
                resultado = self._executor(cmd, cfg.timeout_segundos)
            except FileNotFoundError as exc:
                raise ErroProcessamentoMidia(
                    f"Binário '{self._binario_ffmpeg}' não encontrado no ambiente."
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise ErroProcessamentoMidia(
                    f"Processamento de vídeo excedeu o limite de {cfg.timeout_segundos}s."
                ) from exc

            if resultado.returncode != 0:
                detalhe = (resultado.stderr or resultado.stdout or "").strip()[:400]
                raise ErroProcessamentoMidia(
                    f"FFmpeg falhou (código {resultado.returncode}): {detalhe}"
                )
            if not caminho_saida.exists() or caminho_saida.stat().st_size == 0:
                raise ErroProcessamentoMidia("FFmpeg finalizou sem gerar arquivo de saída.")
            return caminho_saida.read_bytes()
