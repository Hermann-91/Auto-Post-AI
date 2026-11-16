"""Entidades de configuração de IA, base RAG e registro de custos OpenRouter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG


@dataclass(slots=True)
class ConfigIAConta:
    """Persona, templates visuais e preferências de modelo por conta Instagram."""

    empresa_id: UUID
    conta_ig_id: UUID
    persona_json: dict[str, Any] = field(default_factory=dict)
    templates_json: dict[str, Any] = field(default_factory=dict)
    brand_bible_json: dict[str, Any] = field(default_factory=dict)
    aplicar_logo_padrao: bool = False
    modelo_texto_pref: str = "deepseek/deepseek-v4-flash"
    modelo_img_pref: str = "google/gemini-3.1-flash-image"
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class FonteRAG:
    """Documento ou FAQ segmentado em chunks isolados por conta Instagram."""

    empresa_id: UUID
    conta_ig_id: UUID
    tipo: TipoFonteRAG
    titulo: str
    conteudo_limpo: str
    chunks: list[str] = field(default_factory=list)
    resumo_fatos: str = ""
    embeddings_chunks: list[list[float]] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.titulo = self.titulo.strip()
        self.resumo_fatos = self.resumo_fatos.strip()
        if not self.titulo or not self.conteudo_limpo.strip():
            raise ErroValidacaoDominio("Fonte RAG exige título e conteúdo.")
        if (
            self.embeddings_chunks
            and self.chunks
            and len(self.embeddings_chunks) != len(self.chunks)
        ):
            raise ErroValidacaoDominio(
                "Embeddings e chunks da fonte RAG devem ter o mesmo tamanho."
            )


@dataclass(slots=True)
class RegistroCustoIA:
    """Auditoria de consumo de tokens e custo real em USD via OpenRouter."""

    empresa_id: UUID
    conta_ig_id: UUID
    openrouter_gen_id: str
    modelo: str
    tokens_in: int
    tokens_out: int
    custo_usd: Decimal
    postagem_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.tokens_in < 0 or self.tokens_out < 0 or self.custo_usd < Decimal("0"):
            raise ErroValidacaoDominio("Tokens e custo USD não podem ser negativos.")
