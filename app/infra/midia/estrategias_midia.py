"""Estratégias de processamento determinístico de mídia via Strategy + DI."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoMidia
from app.dominio.portas.midia_storage import MidiaStrategyPort
from app.infra.midia.compositor_capa import CompositorCapa, ConfiguracaoCapa
from app.infra.midia.editor_video import ConfiguracaoVideo, EditorVideo
from app.infra.midia.gerador_carrossel import ConfiguracaoCarrossel, GeradorCarrossel
from app.infra.midia.processador_imagem import ProcessadorImagem


def _extrair_proporcao(parametros: dict[str, Any], padrao: str, permitidas: set[str]) -> str:
    proporcao = str(parametros.get("proporcao", padrao))
    if proporcao not in permitidas:
        opcoes = ", ".join(sorted(permitidas))
        raise ErroValidacaoDominio(
            f"Proporção '{proporcao}' não permitida para este formato. Use: {opcoes}."
        )
    return proporcao


def _resolver_logo(parametros: dict[str, Any]) -> bytes | None:
    aplicar_logo = parametros.get("aplicar_logo")
    logo = parametros.get("logo_bytes")
    if aplicar_logo is False:
        return None
    if logo is not None and not isinstance(logo, bytes):
        raise ErroValidacaoDominio("Parâmetro 'logo_bytes' deve estar em bytes.")
    if aplicar_logo is True and not logo:
        raise ErroValidacaoDominio("Logotipo é obrigatório quando 'aplicar_logo=True'.")
    return logo


def _validar_unico_arquivo(arquivos_bytes: list[bytes], formato: str) -> bytes:
    if len(arquivos_bytes) != 1:
        raise ErroValidacaoDominio(f"Formato {formato} exige exatamente 1 arquivo de mídia.")
    return arquivos_bytes[0]


def _eh_video_bytes(dados: bytes, parametros: dict[str, Any]) -> bool:
    eh_video = parametros.get("eh_video")
    if isinstance(eh_video, bool):
        return eh_video
    content_type = str(parametros.get("content_type", "")).strip().lower()
    if content_type.startswith("video/"):
        return True
    if content_type.startswith("image/"):
        return False
    return len(dados) >= 12 and dados[4:8] == b"ftyp"


async def _processar_imagem_unica(
    compositor: CompositorCapa,
    foto: bytes,
    proporcao: str,
    parametros: dict[str, Any],
) -> list[bytes]:
    logo = _resolver_logo(parametros)
    aplicar_gradiente = bool(parametros.get("aplicar_gradiente", logo is not None))
    if logo is not None or aplicar_gradiente:
        cfg = ConfiguracaoCapa(aplicar_gradiente=aplicar_gradiente)
        saida = await asyncio.to_thread(compositor.compor, foto, logo, cfg, proporcao)
    else:
        saida = await asyncio.to_thread(ProcessadorImagem.otimizar_para_formato, foto, proporcao)
    return [saida]


class EstrategiaImagemFeed:
    """Estratégia determinística para postagem única no feed (IMAGE)."""

    tipo_suportado: TipoMidia = TipoMidia.IMAGE

    def __init__(self, compositor: CompositorCapa | None = None) -> None:
        self._compositor = compositor or CompositorCapa()

    async def processar(
        self,
        arquivos_bytes: list[bytes],
        parametros: dict[str, Any],
    ) -> list[bytes]:
        foto = _validar_unico_arquivo(arquivos_bytes, self.tipo_suportado.value)
        proporcao = _extrair_proporcao(parametros, "4:5", {"4:5", "1:1"})
        return await _processar_imagem_unica(self._compositor, foto, proporcao, parametros)


class EstrategiaCarrossel:
    """Estratégia determinística para sequência de slides (CAROUSEL)."""

    tipo_suportado: TipoMidia = TipoMidia.CAROUSEL

    def __init__(self, gerador: GeradorCarrossel | None = None) -> None:
        self._gerador = gerador or GeradorCarrossel()

    async def processar(
        self,
        arquivos_bytes: list[bytes],
        parametros: dict[str, Any],
    ) -> list[bytes]:
        proporcao = _extrair_proporcao(parametros, "4:5", {"4:5", "1:1"})
        logo = _resolver_logo(parametros)
        cfg = ConfiguracaoCarrossel(
            proporcao=proporcao,
            aplicar_gradiente=bool(parametros.get("aplicar_gradiente", True)),
            incluir_slide_encerramento=bool(parametros.get("incluir_slide_encerramento", False)),
        )
        return await asyncio.to_thread(self._gerador.gerar_slides, arquivos_bytes, logo, cfg)


class EstrategiaReels:
    """Estratégia determinística para vídeos verticais 9:16 (REELS)."""

    tipo_suportado: TipoMidia = TipoMidia.REELS

    def __init__(self, editor: EditorVideo | None = None) -> None:
        self._editor = editor or EditorVideo()

    async def processar(
        self,
        arquivos_bytes: list[bytes],
        parametros: dict[str, Any],
    ) -> list[bytes]:
        video = _validar_unico_arquivo(arquivos_bytes, self.tipo_suportado.value)
        proporcao = _extrair_proporcao(parametros, "9:16", {"9:16"})
        logo = _resolver_logo(parametros)
        cfg = ConfiguracaoVideo(proporcao=proporcao)
        return [await asyncio.to_thread(self._editor.processar_video, video, logo, cfg)]


class EstrategiaStories:
    """Estratégia determinística para foto ou vídeo vertical 9:16 (STORIES)."""

    tipo_suportado: TipoMidia = TipoMidia.STORIES

    def __init__(
        self, compositor: CompositorCapa | None = None, editor: EditorVideo | None = None
    ) -> None:
        self._compositor = compositor or CompositorCapa()
        self._editor = editor or EditorVideo()

    async def processar(
        self,
        arquivos_bytes: list[bytes],
        parametros: dict[str, Any],
    ) -> list[bytes]:
        ativo = _validar_unico_arquivo(arquivos_bytes, self.tipo_suportado.value)
        proporcao = _extrair_proporcao(parametros, "9:16", {"9:16"})
        if _eh_video_bytes(ativo, parametros):
            logo = _resolver_logo(parametros)
            cfg_video = ConfiguracaoVideo(proporcao=proporcao)
            return [await asyncio.to_thread(self._editor.processar_video, ativo, logo, cfg_video)]
        return await _processar_imagem_unica(self._compositor, ativo, proporcao, parametros)


class FabricaEstrategiasMidia:
    """Registry/Factory extensível (OCP) que resolve estratégias por TipoMidia."""

    def __init__(
        self,
        compositor: CompositorCapa | None = None,
        gerador_carrossel: GeradorCarrossel | None = None,
        editor_video: EditorVideo | None = None,
    ) -> None:
        comp = compositor or CompositorCapa()
        gerador = gerador_carrossel or GeradorCarrossel(comp)
        editor = editor_video or EditorVideo()
        estrategias: Sequence[MidiaStrategyPort] = (
            EstrategiaImagemFeed(comp), EstrategiaCarrossel(gerador),
            EstrategiaReels(editor), EstrategiaStories(comp, editor),
        )
        self._estrategias: dict[TipoMidia, MidiaStrategyPort] = {e.tipo_suportado: e
                                                                 for e in estrategias}

    def registrar(self, estrategia: MidiaStrategyPort) -> None:
        """Permite registrar ou substituir estratégia para um formato."""
        self._estrategias[estrategia.tipo_suportado] = estrategia

    def obter(self, tipo: TipoMidia) -> MidiaStrategyPort:
        """Retorna a estratégia correspondente ao TipoMidia solicitado."""
        estrategia = self._estrategias.get(tipo)
        if estrategia is None:
            raise ErroValidacaoDominio(f"Nenhuma estratégia registrada para {tipo.value}.")
        return estrategia

    async def processar(
        self,
        tipo: TipoMidia,
        arquivos_bytes: list[bytes],
        parametros: dict[str, Any] | None = None,
    ) -> list[bytes]:
        """Despacha o processamento para a estratégia correta via DI."""
        return await self.obter(tipo).processar(arquivos_bytes, parametros or {})
