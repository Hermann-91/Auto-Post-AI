"""Repositório SQLAlchemy Async para postagens multi-formato e fila de agendamento."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dominio.entidades.publicacao import Postagem
from app.dominio.excecoes import ErroConflitoDados
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem, TipoMidia
from app.infra.db.modelos_conteudo import PostagemModel
from app.infra.db.repo_custo_sql import SqlCustoRepository

__all__ = ["SqlCustoRepository", "SqlPostagemRepository"]


def _para_postagem(m: PostagemModel) -> Postagem:
    return Postagem(
        id=m.id,
        empresa_id=m.empresa_id,
        conta_ig_id=m.conta_ig_id,
        tipo_midia=TipoMidia(m.tipo_midia),
        midias_chaves=list(m.midias_json),
        legenda=m.legenda,
        status=StatusPostagem(m.status),
        planejamento_id=m.planejamento_id,
        agendado_para=m.agendado_para,
        idempotency_key=m.idempotency_key,
        meta_container_id=m.meta_container_id,
        meta_media_id=m.meta_media_id,
        erro_detalhe=m.erro_detalhe,
        criado_em=m.criado_em,
        tentativas_publicacao=m.tentativas_publicacao,
        atualizado_em=m.atualizado_em,
    )


class SqlPostagemRepository:
    """Persistência SQL de postagens multi-formato e fila de agendamento."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def salvar(self, postagem: Postagem) -> Postagem:
        modelo = PostagemModel(
            id=postagem.id,
            empresa_id=postagem.empresa_id,
            conta_ig_id=postagem.conta_ig_id,
            planejamento_id=postagem.planejamento_id,
            tipo_midia=postagem.tipo_midia.value,
            midias_json=postagem.midias_chaves,
            legenda=postagem.legenda,
            status=postagem.status.value,
            agendado_para=postagem.agendado_para,
            idempotency_key=postagem.idempotency_key,
            meta_container_id=postagem.meta_container_id,
            meta_media_id=postagem.meta_media_id,
            erro_detalhe=postagem.erro_detalhe,
            criado_em=postagem.criado_em,
            tentativas_publicacao=postagem.tentativas_publicacao,
            atualizado_em=postagem.atualizado_em,
        )
        try:
            async with self._sf() as session, session.begin():
                await session.merge(modelo)
        except IntegrityError as exc:
            raise ErroConflitoDados("Chave de idempotência de postagem duplicada.") from exc
        return postagem

    async def buscar_por_id(
        self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID
    ) -> Postagem | None:
        async with self._sf() as session:
            stmt = select(PostagemModel).where(
                PostagemModel.id == postagem_id,
                PostagemModel.empresa_id == empresa_id,
                PostagemModel.conta_ig_id == conta_ig_id,
            )
            modelo = await session.scalar(stmt)
            return _para_postagem(modelo) if modelo is not None else None

    async def listar_por_conta(
        self, empresa_id: UUID, conta_ig_id: UUID, status: StatusPostagem | None = None
    ) -> list[Postagem]:
        async with self._sf() as session:
            stmt = select(PostagemModel).where(
                PostagemModel.empresa_id == empresa_id,
                PostagemModel.conta_ig_id == conta_ig_id,
            )
            if status is not None:
                stmt = stmt.where(PostagemModel.status == status.value)
            stmt = stmt.order_by(PostagemModel.criado_em.desc())
            modelos = (await session.scalars(stmt)).all()
            return [_para_postagem(m) for m in modelos]

    async def listar_agendadas_pendentes(self, ate_momento: datetime) -> list[Postagem]:
        async with self._sf() as session:
            stmt = (
                select(PostagemModel)
                .where(
                    PostagemModel.status == StatusPostagem.AGENDADO.value,
                    PostagemModel.agendado_para.is_not(None),
                    PostagemModel.agendado_para <= ate_momento,
                )
                .order_by(PostagemModel.agendado_para.asc())
            )
            modelos = (await session.scalars(stmt)).all()
            return [_para_postagem(m) for m in modelos]

    async def listar_publicando_travadas(self, atualizado_ate: datetime) -> list[Postagem]:
        async with self._sf() as session:
            stmt = (
                select(PostagemModel)
                .where(
                    PostagemModel.status == StatusPostagem.PUBLICANDO.value,
                    PostagemModel.atualizado_em <= atualizado_ate,
                )
                .order_by(PostagemModel.atualizado_em.asc())
            )
            modelos = (await session.scalars(stmt)).all()
            return [_para_postagem(m) for m in modelos]

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID) -> bool:
        async with self._sf() as session, session.begin():
            stmt = delete(PostagemModel).where(
                PostagemModel.id == postagem_id,
                PostagemModel.empresa_id == empresa_id,
                PostagemModel.conta_ig_id == conta_ig_id,
            )
            res = await session.execute(stmt)
            return bool(cast(CursorResult[Any], res).rowcount)
