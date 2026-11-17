"""Repositórios SQLAlchemy Async para ConfigIA e RAG (re-exporta Planejamento)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dominio.entidades.ia_rag import ConfigIAConta, FonteRAG
from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG
from app.infra.db.modelos_conteudo import (
    ConfigIAContaModel,
    FonteRAGModel,
)
from app.infra.db.repo_planejamento_sql import SqlPlanejamentoRepository, remover_por_conta

__all__ = [
    "SqlConfigIARepository",
    "SqlPlanejamentoRepository",
    "SqlRagRepository",
]


def _para_config(m: ConfigIAContaModel) -> ConfigIAConta:
    return ConfigIAConta(
        id=m.id,
        empresa_id=m.empresa_id,
        conta_ig_id=m.conta_ig_id,
        persona_json=dict(m.persona_json),
        templates_json=dict(m.templates_json),
        brand_bible_json=dict(m.brand_bible_json or {}),
        aplicar_logo_padrao=m.aplicar_logo_padrao,
        modelo_texto_pref=m.modelo_texto_pref,
        modelo_img_pref=m.modelo_img_pref,
    )


def _para_rag(m: FonteRAGModel) -> FonteRAG:
    return FonteRAG(
        id=m.id,
        empresa_id=m.empresa_id,
        conta_ig_id=m.conta_ig_id,
        tipo=TipoFonteRAG(m.tipo),
        titulo=m.titulo,
        conteudo_limpo=m.conteudo_limpo,
        chunks=list(m.chunks_json),
        resumo_fatos=m.resumo_fatos or "",
        embeddings_chunks=[[float(x) for x in v] for v in (m.embeddings_chunks_json or [])],
        criado_em=m.criado_em,
    )


class SqlConfigIARepository:
    """Persistência SQL de preferências de IA e persona por conta Instagram."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def obter_ou_padrao(self, empresa_id: UUID, conta_ig_id: UUID) -> ConfigIAConta:
        async with self._sf() as session:
            stmt = select(ConfigIAContaModel).where(
                ConfigIAContaModel.empresa_id == empresa_id,
                ConfigIAContaModel.conta_ig_id == conta_ig_id,
            )
            modelo = await session.scalar(stmt)
            if modelo is None:
                return ConfigIAConta(empresa_id=empresa_id, conta_ig_id=conta_ig_id)
            return _para_config(modelo)

    async def salvar(self, config: ConfigIAConta) -> ConfigIAConta:
        modelo = ConfigIAContaModel(
            id=config.id,
            empresa_id=config.empresa_id,
            conta_ig_id=config.conta_ig_id,
            persona_json=config.persona_json,
            templates_json=config.templates_json,
            brand_bible_json=config.brand_bible_json,
            aplicar_logo_padrao=config.aplicar_logo_padrao,
            modelo_texto_pref=config.modelo_texto_pref,
            modelo_img_pref=config.modelo_img_pref,
        )
        async with self._sf() as session, session.begin():
            await session.merge(modelo)
        return config


class SqlRagRepository:
    """Persistência SQL de fontes de conhecimento RAG por conta Instagram."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def salvar(self, fonte: FonteRAG) -> FonteRAG:
        modelo = FonteRAGModel(
            id=fonte.id,
            empresa_id=fonte.empresa_id,
            conta_ig_id=fonte.conta_ig_id,
            tipo=fonte.tipo.value,
            titulo=fonte.titulo,
            conteudo_limpo=fonte.conteudo_limpo,
            chunks_json=fonte.chunks,
            resumo_fatos=fonte.resumo_fatos,
            embeddings_chunks_json=fonte.embeddings_chunks,
            criado_em=fonte.criado_em,
        )
        async with self._sf() as session, session.begin():
            await session.merge(modelo)
        return fonte

    async def listar_por_conta(self, empresa_id: UUID, conta_ig_id: UUID) -> list[FonteRAG]:
        async with self._sf() as session:
            stmt = (
                select(FonteRAGModel)
                .where(
                    FonteRAGModel.empresa_id == empresa_id,
                    FonteRAGModel.conta_ig_id == conta_ig_id,
                )
                .order_by(FonteRAGModel.criado_em.desc())
            )
            modelos = (await session.scalars(stmt)).all()
            return [_para_rag(m) for m in modelos]

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, fonte_id: UUID) -> bool:
        return await remover_por_conta(self._sf, FonteRAGModel, fonte_id, empresa_id, conta_ig_id)
