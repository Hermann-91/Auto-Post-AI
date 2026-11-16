"""Pesquisa web de tendências e blueprints por nicho/região com cache 24h-72h."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.ia.buscador_web_real import BuscadorWebPort, BuscadorWebReal
from app.infra.ia.cache_tendencias import (
    CacheTendenciasMemoria,
    CacheTendenciasPort,
    CacheTendenciasRedis,
    ClienteRedisCachePort,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BuscadorWebPort",
    "BuscadorWebReal",
    "CacheTendenciasMemoria",
    "CacheTendenciasPort",
    "CacheTendenciasRedis",
    "ClienteRedisCachePort",
    "PesquisaTendenciasAdapter",
]


class PesquisaTendenciasAdapter:
    """Orquestra pesquisa web de tendências com cache obrigatório entre 24h e 72h."""

    def __init__(
        self,
        cache: CacheTendenciasPort | None = None,
        buscador: BuscadorWebPort | None = None,
    ) -> None:
        self._cache = cache or CacheTendenciasMemoria()
        self._buscador = buscador or BuscadorWebReal()

    @staticmethod
    def _chave_cache(nicho: str, regiao: str) -> str:
        nicho_norm = " ".join(nicho.lower().split())
        regiao_norm = " ".join(regiao.lower().split())
        return f"tendencias:{nicho_norm}:{regiao_norm}"

    async def buscar_tendencias(
        self,
        nicho: str,
        regiao: str,
        ttl_horas: int = 48,
    ) -> dict[str, Any]:
        """Retorna tendências em cache ou consulta web respeitando janela 24h a 72h."""
        nicho_limpo = nicho.strip()
        if not nicho_limpo:
            raise ErroValidacaoDominio("Nicho é obrigatório para pesquisa de tendências.")
        regiao_limpa = regiao.strip() or "Brasil"
        ttl_efetivo = max(24, min(72, ttl_horas))

        chave = self._chave_cache(nicho_limpo, regiao_limpa)
        em_cache = await self._cache.obter(chave)
        if em_cache is not None:
            em_cache["cache_hit"] = True
            return em_cache

        fonte = "web"
        try:
            topicos = await self._buscador.buscar(nicho_limpo, regiao_limpa)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Busca web de tendências falhou (%s); usando base offline.",
                type(exc).__name__,
            )
            topicos = []
            fonte = "fallback_offline"

        if not topicos:
            topicos = [
                {
                    "titulo": f"Conteúdo educativo em {nicho_limpo}",
                    "resumo": (
                        "Dicas práticas e bastidores reais para audiência de "
                        f"{regiao_limpa}."
                    ),
                    "url": "",
                },
                {
                    "titulo": f"Prova social e rotina de {nicho_limpo}",
                    "resumo": "Carrosséis comparativos e Reels curtos com gancho nos 3s iniciais.",
                    "url": "",
                },
            ]
            if fonte == "web":
                fonte = "fallback_vazio"

        payload: dict[str, Any] = {
            "nicho": nicho_limpo,
            "regiao": regiao_limpa,
            "fonte": fonte,
            "cache_hit": False,
            "ttl_horas": ttl_efetivo,
            "consultado_em": datetime.now(UTC).isoformat(),
            "topicos": topicos,
        }
        ttl_cache_seg = ttl_efetivo * 3600 if fonte == "web" else 3600
        await self._cache.definir(chave, payload, ttl_segundos=ttl_cache_seg)
        return payload
