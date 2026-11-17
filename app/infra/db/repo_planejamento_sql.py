"""Repositório SQLAlchemy Async para Planejamento Semanal e helper de remoção por conta."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dominio.entidades.publicacao import PlanejamentoSemanal
from app.dominio.objetos_valor.enums_conteudo import StatusPlanejamento
from app.infra.db.modelos_conteudo import PlanejamentoSemanalModel


async def remover_por_conta(
    session_factory: async_sessionmaker[AsyncSession],
    modelo: type[Any],
    registro_id: UUID,
    empresa_id: UUID,
    conta_ig_id: UUID,
) -> bool:
    """Remove um registro isolado por (id, empresa_id, conta_ig_id) e indica se existia."""
    async with session_factory() as session, session.begin():
        stmt = delete(modelo).where(
            modelo.id == registro_id,
            modelo.empresa_id == empresa_id,
            modelo.conta_ig_id == conta_ig_id,
        )
        res = await session.execute(stmt)
        return int(getattr(res, "rowcount", 0) or 0) > 0


def _para_planejamento(m: PlanejamentoSemanalModel) -> PlanejamentoSemanal:
    return PlanejamentoSemanal(
        id=m.id,
        empresa_id=m.empresa_id,
        conta_ig_id=m.conta_ig_id,
        semana_inicio=m.semana_inicio,
        itens_grade=list(m.itens_grade_json),
        tendencias_cache=dict(m.tendencias_cache_json),
        custo_estimado_usd=m.custo_estimado_usd,
        status=StatusPlanejamento(m.status),
        criado_em=m.criado_em,
    )


class SqlPlanejamentoRepository:
    """Persistência SQL de planejamentos semanais por conta Instagram."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def salvar(self, plano: PlanejamentoSemanal) -> PlanejamentoSemanal:
        modelo = PlanejamentoSemanalModel(
            id=plano.id,
            empresa_id=plano.empresa_id,
            conta_ig_id=plano.conta_ig_id,
            semana_inicio=plano.semana_inicio,
            itens_grade_json=plano.itens_grade,
            tendencias_cache_json=plano.tendencias_cache,
            custo_estimado_usd=plano.custo_estimado_usd,
            status=plano.status.value,
            criado_em=plano.criado_em,
        )
        async with self._sf() as session, session.begin():
            await session.merge(modelo)
        return plano

    async def buscar_por_id(
        self, empresa_id: UUID, conta_ig_id: UUID, plano_id: UUID
    ) -> PlanejamentoSemanal | None:
        async with self._sf() as session:
            stmt = select(PlanejamentoSemanalModel).where(
                PlanejamentoSemanalModel.id == plano_id,
                PlanejamentoSemanalModel.empresa_id == empresa_id,
                PlanejamentoSemanalModel.conta_ig_id == conta_ig_id,
            )
            modelo = await session.scalar(stmt)
            return _para_planejamento(modelo) if modelo is not None else None

    async def listar_por_conta(
        self, empresa_id: UUID, conta_ig_id: UUID
    ) -> list[PlanejamentoSemanal]:
        async with self._sf() as session:
            stmt = (
                select(PlanejamentoSemanalModel)
                .where(
                    PlanejamentoSemanalModel.empresa_id == empresa_id,
                    PlanejamentoSemanalModel.conta_ig_id == conta_ig_id,
                )
                .order_by(PlanejamentoSemanalModel.semana_inicio.desc())
            )
            modelos = (await session.scalars(stmt)).all()
            return [_para_planejamento(m) for m in modelos]

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, plano_id: UUID) -> bool:
        return await remover_por_conta(
            self._sf, PlanejamentoSemanalModel, plano_id, empresa_id, conta_ig_id
        )
