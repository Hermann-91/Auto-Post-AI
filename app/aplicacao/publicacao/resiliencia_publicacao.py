"""Helpers de resiliência: retry com backoff exponencial e recuperação de PUBLICANDO."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import UUID

from app.aplicacao.publicacao.dtos import ResultadoPublicacaoDTO
from app.dominio.entidades.publicacao import Postagem
from app.dominio.excecoes import (
    ErroDominio,
    ErroIntegracaoMeta,
    ErroLimitePublicacaoMeta,
)
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem
from app.dominio.portas.repositorios_conteudo import PostagemRepositoryPort

logger = logging.getLogger(__name__)


def calcular_atraso_backoff_segundos(tentativa_atual: int, base_segundos: int) -> int:
    """Calcula backoff exponencial em segundos a partir do número de tentativas prévias."""
    expoente = min(10, max(0, tentativa_atual))
    return max(1, base_segundos) * (1 << expoente)


def extrair_token_plano(token_descriptografado: str) -> str:
    """Remove aspas e prefixo Bearer eventual antes do uso na Graph API."""
    bruto = token_descriptografado.strip().strip("\"'")
    return bruto[7:].strip() if bruto.lower().startswith("bearer ") else bruto


def tratar_erro_integracao_meta(
    post: Postagem,
    exc: ErroIntegracaoMeta,
    agora: datetime,
    max_tentativas: int,
    backoff_base_segundos: int,
) -> ResultadoPublicacaoDTO:
    """Reagenda com backoff exponencial em erro transitório ou marca FALHA ao esgotar teto."""
    if exc.transitorio and (post.tentativas_publicacao + 1) < max(1, max_tentativas):
        atraso = calcular_atraso_backoff_segundos(post.tentativas_publicacao, backoff_base_segundos)
        proxima = agora + timedelta(seconds=atraso)
        post.reagendar_por_falha_transitoria(proxima, str(exc), agora=agora)
        return ResultadoPublicacaoDTO(
            postagem=post,
            publicada=False,
            reagendada=True,
            motivo=f"Erro transitório Meta (retry em {atraso}s): {exc}",
        )
    detalhe = str(exc)
    if exc.transitorio and post.tentativas_publicacao > 0:
        detalhe = f"Falha após {post.tentativas_publicacao + 1} tentativas: {exc}"
    post.marcar_falha(detalhe, agora=agora)
    return ResultadoPublicacaoDTO(
        postagem=post,
        publicada=False,
        motivo=post.erro_detalhe or str(exc),
    )


def tratar_excecao_publicacao(
    post: Postagem,
    exc: Exception,
    agora: datetime,
    reagendar_cota_minutos: int,
    max_tentativas: int,
    backoff_base_segundos: int,
) -> ResultadoPublicacaoDTO:
    """Aplica política uniforme de transição para erros Meta, domínio e inesperados."""
    if isinstance(exc, ErroLimitePublicacaoMeta):
        post.marcar_falha(str(exc), agora=agora)
        post.agendar(agora + timedelta(minutes=reagendar_cota_minutos), agora=agora)
        return ResultadoPublicacaoDTO(
            postagem=post, publicada=False, reagendada=True, motivo=str(exc)
        )
    if isinstance(exc, ErroIntegracaoMeta):
        return tratar_erro_integracao_meta(
            post, exc, agora, max_tentativas, backoff_base_segundos
        )
    if isinstance(exc, ErroDominio):
        post.marcar_falha(str(exc), agora=agora)
        return ResultadoPublicacaoDTO(postagem=post, publicada=False, motivo=str(exc))

    logger.exception("Erro inesperado ao publicar postagem %s", post.id)
    post.marcar_falha(f"Erro interno na publicação: {type(exc).__name__}", agora=agora)
    return ResultadoPublicacaoDTO(
        postagem=post,
        publicada=False,
        motivo=post.erro_detalhe or "Erro interno.",
    )


async def recuperar_postagem_travada(
    post_repo: PostagemRepositoryPort,
    empresa_id: UUID,
    conta_ig_id: UUID,
    postagem_id: UUID,
    limite_travamento: datetime,
    agora: datetime,
    max_tentativas: int,
) -> bool:
    """Reencaminha postagem presa em PUBLICANDO além do TTL para AGENDADO ou FALHA."""
    atual = await post_repo.buscar_por_id(empresa_id, conta_ig_id, postagem_id)
    if (
        atual is None
        or atual.status != StatusPostagem.PUBLICANDO
        or atual.atualizado_em > limite_travamento
    ):
        return False

    if (atual.tentativas_publicacao + 1) < max(1, max_tentativas):
        atual.reagendar_por_falha_transitoria(
            agora,
            "Recuperado automaticamente após travamento em PUBLICANDO além do TTL do lock.",
            agora=agora,
        )
    else:
        atual.marcar_falha(
            f"Excedido limite de {max(1, max_tentativas)} tentativas após travamento.",
            agora=agora,
        )
    await post_repo.salvar(atual)
    return True
