"""Estratégias Meta Graph API (Strategy + DI) para IMAGE, CAROUSEL, REELS e STORIES."""

from __future__ import annotations

from typing import Any

from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroLimitePublicacaoMeta, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoMidia
from app.dominio.portas.ia_meta import PublicadorMidiaStrategyPort
from app.infra.meta.cliente_meta_http import ClienteMetaHttp
from app.infra.meta.modelos_meta import eh_video_midia, validar_urls_publicas

__all__ = [
    "CarrosselPublicacaoStrategy",
    "FabricaPublicadoresMeta",
    "FotoPublicacaoStrategy",
    "ReelsPublicacaoStrategy",
    "StoriesPublicacaoStrategy",
    "validar_urls_publicas",
]


async def _checar_cota_meta(cliente: ClienteMetaHttp, conta: ContaInstagram, token: str) -> None:
    limite = await cliente.consultar_limite_publicacao(conta.ig_user_id, token)
    if limite.atingido:
        raise ErroLimitePublicacaoMeta(
            f"Limite diário da Meta atingido ({limite.quota_usage}/{limite.quota_total})."
        )


def _anexar_legenda(payload: dict[str, Any], legenda: str) -> dict[str, Any]:
    if legenda.strip():
        payload["caption"] = legenda
    return payload


async def _finalizar_publicacao(
    cliente: ClienteMetaHttp, conta: ContaInstagram, token: str, container_id: str
) -> tuple[str, str]:
    estado = await cliente.aguardar_container_pronto(container_id, token)
    if estado.status_code == "PUBLISHED":
        return f"published:{container_id}", container_id
    media_id = await cliente.publicar_container(conta.ig_user_id, token, container_id)
    return media_id, container_id


async def _publicar_simples(
    cliente: ClienteMetaHttp,
    conta: ContaInstagram,
    token: str,
    postagem: Postagem,
    payload: dict[str, Any],
) -> tuple[str, str]:
    await _checar_cota_meta(cliente, conta, token)
    container_id = postagem.meta_container_id
    if container_id:
        estado = await cliente.consultar_status_container(container_id, token)
        if estado.status_code == "PUBLISHED":
            return f"published:{container_id}", container_id
        if estado.status_code in {"ERROR", "EXPIRED"}:
            container_id = None
    if not container_id:
        container_id = await cliente.criar_container(conta.ig_user_id, token, payload)
    return await _finalizar_publicacao(cliente, conta, token, container_id)


class _BasePublicacaoSimples:
    """Base compartilhada para formatos de mídia única (IMAGE, REELS, STORIES)."""

    def __init__(self, cliente: ClienteMetaHttp, exigir_https: bool = False) -> None:
        self._cliente = cliente
        self._exigir_https = exigir_https

    def _montar_payload(self, url: str, postagem: Postagem) -> dict[str, Any]:
        raise NotImplementedError

    async def publicar(
        self,
        conta: ContaInstagram,
        token_descriptografado: str,
        postagem: Postagem,
        urls_publicas: list[str],
    ) -> tuple[str, str]:
        urls = validar_urls_publicas(urls_publicas, self._exigir_https)
        if len(urls) != 1:
            raise ErroValidacaoDominio(
                f"Estratégia {postagem.tipo_midia.value} exige exatamente 1 URL pública."
            )
        payload = self._montar_payload(urls[0], postagem)
        return await _publicar_simples(
            self._cliente, conta, token_descriptografado, postagem, payload
        )


class FotoPublicacaoStrategy(_BasePublicacaoSimples):
    """Publicação de imagem única JPEG via container Meta."""

    tipo_suportado = TipoMidia.IMAGE

    def _montar_payload(self, url: str, postagem: Postagem) -> dict[str, Any]:
        return _anexar_legenda({"image_url": url}, postagem.legenda)


class ReelsPublicacaoStrategy(_BasePublicacaoSimples):
    """Publicação de vídeo vertical 9:16 no formato REELS."""

    tipo_suportado = TipoMidia.REELS

    def _montar_payload(self, url: str, postagem: Postagem) -> dict[str, Any]:
        base: dict[str, Any] = {"media_type": "REELS", "video_url": url, "share_to_feed": True}
        return _anexar_legenda(base, postagem.legenda)


class StoriesPublicacaoStrategy(_BasePublicacaoSimples):
    """Publicação 9:16 em STORIES (sem legenda textual)."""

    tipo_suportado = TipoMidia.STORIES

    def _montar_payload(self, url: str, postagem: Postagem) -> dict[str, Any]:
        eh_vid = eh_video_midia(postagem.midias_chaves[0]) or eh_video_midia(url)
        return {"media_type": "STORIES", "video_url" if eh_vid else "image_url": url}


class CarrosselPublicacaoStrategy:
    """Publicação em 2 sub-etapas de carrossel (2 a 10 itens)."""

    tipo_suportado = TipoMidia.CAROUSEL

    def __init__(self, cliente: ClienteMetaHttp, exigir_https: bool = False) -> None:
        self._cliente = cliente
        self._exigir_https = exigir_https

    async def publicar(
        self,
        conta: ContaInstagram,
        token_descriptografado: str,
        postagem: Postagem,
        urls_publicas: list[str],
    ) -> tuple[str, str]:
        urls = validar_urls_publicas(urls_publicas, self._exigir_https)
        if not 2 <= len(urls) <= 10:
            raise ErroValidacaoDominio("Carrossel exige entre 2 e 10 URLs públicas.")
        await _checar_cota_meta(self._cliente, conta, token_descriptografado)

        filhos_ids: list[str] = []
        for idx, url in enumerate(urls):
            chave_ref = postagem.midias_chaves[idx] if idx < len(postagem.midias_chaves) else url
            payload_item: dict[str, Any] = {"is_carousel_item": True}
            if eh_video_midia(chave_ref) or eh_video_midia(url):
                payload_item["media_type"] = "VIDEO"
                payload_item["video_url"] = url
            else:
                payload_item["image_url"] = url
            filho_id = await self._cliente.criar_container(
                conta.ig_user_id, token_descriptografado, payload_item
            )
            await self._cliente.aguardar_container_pronto(filho_id, token_descriptografado)
            filhos_ids.append(filho_id)

        payload_pai = _anexar_legenda(
            {"media_type": "CAROUSEL", "children": filhos_ids}, postagem.legenda
        )
        pai_id = await self._cliente.criar_container(
            conta.ig_user_id, token_descriptografado, payload_pai
        )
        return await _finalizar_publicacao(
            self._cliente, conta, token_descriptografado, pai_id
        )


class FabricaPublicadoresMeta:
    """Resolve dinamicamente a estratégia de publicação Meta pelo TipoMidia."""

    def __init__(self, cliente: ClienteMetaHttp, exigir_https: bool = False) -> None:
        estrategias: tuple[PublicadorMidiaStrategyPort, ...] = (
            FotoPublicacaoStrategy(cliente, exigir_https),
            CarrosselPublicacaoStrategy(cliente, exigir_https),
            ReelsPublicacaoStrategy(cliente, exigir_https),
            StoriesPublicacaoStrategy(cliente, exigir_https),
        )
        self._mapa: dict[TipoMidia, PublicadorMidiaStrategyPort] = {
            est.tipo_suportado: est for est in estrategias
        }

    def obter(self, tipo_midia: TipoMidia) -> PublicadorMidiaStrategyPort:
        """Retorna estratégia compatível ou falha explicitamente."""
        estrategia = self._mapa.get(tipo_midia)
        if estrategia is None:
            raise ErroValidacaoDominio(f"Tipo de mídia sem estratégia Meta: {tipo_midia.value}.")
        return estrategia
