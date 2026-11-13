"""Enumerações ligadas a biblioteca de mídia, RAG, postagens e planejamento."""

from __future__ import annotations

from enum import StrEnum


class TipoMidia(StrEnum):
    """Formatos oficiais de publicação suportados via Strategy + DI."""

    IMAGE = "IMAGE"
    CAROUSEL = "CAROUSEL"
    REELS = "REELS"
    STORIES = "STORIES"


class PastaMidia(StrEnum):
    """Subdiretórios padronizados no storage R2/S3 por conta Instagram."""

    ORIGINAIS = "originais"
    PROCESSADAS = "processadas"
    IA_CRIA = "IA-Cria"
    IA_EDITA = "IA-Edita"


class StatusPostagem(StrEnum):
    """Estados do ciclo de vida de uma postagem."""

    RASCUNHO = "RASCUNHO"
    AGENDADO = "AGENDADO"
    PUBLICANDO = "PUBLICANDO"
    PUBLICADO = "PUBLICADO"
    FALHA = "FALHA"
    CANCELADO = "CANCELADO"


class StatusPlanejamento(StrEnum):
    """Estados do fluxo em duas etapas do planejamento semanal."""

    RASCUNHO = "RASCUNHO"
    AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO"
    APROVADO = "APROVADO"
    EM_EXECUCAO = "EM_EXECUCAO"
    CONCLUIDO = "CONCLUIDO"
    FALHA = "FALHA"
    CANCELADO = "CANCELADO"


class TipoFonteRAG(StrEnum):
    """Tipos de conhecimento indexados por conta Instagram."""

    TEXTO = "TEXTO"
    DOCUMENTO = "DOCUMENTO"
    FAQ = "FAQ"
    LINK = "LINK"
