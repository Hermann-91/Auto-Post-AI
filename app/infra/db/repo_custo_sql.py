"""Repositório SQLAlchemy Async para auditoria e soma mensal de custos de IA."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dominio.entidades.ia_rag import RegistroCustoIA
from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.db.modelos_conteudo import RegistroCustoIAModel


def _para_custo(m: RegistroCustoIAModel) -> RegistroCustoIA:
    return RegistroCustoIA(
        id=m.id,
        empresa_id=m.empresa_id,
        conta_ig_id=m.conta_ig_id,
        postagem_id=m.postagem_id,
        openrouter_gen_id=m.openrouter_gen_id,
        modelo=m.modelo,
        tokens_in=m.tokens_in,
        tokens_out=m.tokens_out,
        custo_usd=m.custo_usd,
        criado_em=m.criado_em,
    )


class SqlCustoRepository:
    """Persistência SQL e agregação mensal de gastos OpenRouter por empresa."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def registrar(self, registro: RegistroCustoIA) -> RegistroCustoIA:
        modelo = RegistroCustoIAModel(
            id=registro.id,
            empresa_id=registro.empresa_id,
            conta_ig_id=registro.conta_ig_id,
            postagem_id=registro.postagem_id,
            openrouter_gen_id=registro.openrouter_gen_id,
            modelo=registro.modelo,
            tokens_in=registro.tokens_in,
            tokens_out=registro.tokens_out,
            custo_usd=registro.custo_usd,
            criado_em=registro.criado_em,
        )
        async with self._sf() as session, session.begin():
            session.add(modelo)
        return _para_custo(modelo)

    @staticmethod
    def _intervalo_mes(ano: int, mes: int) -> tuple[datetime, datetime]:
        if not 1 <= mes <= 12:
            raise ErroValidacaoDominio("Mês deve estar entre 1 e 12.")
        inicio = datetime(ano, mes, 1, tzinfo=UTC)
        fim = (
            datetime(ano + 1, 1, 1, tzinfo=UTC)
            if mes == 12
            else datetime(ano, mes + 1, 1, tzinfo=UTC)
        )
        return inicio, fim

    async def _somar_periodo(
        self, empresa_id: UUID, ano: int, mes: int, conta_ig_id: UUID | None = None
    ) -> Decimal:
        inicio, fim = self._intervalo_mes(ano, mes)
        async with self._sf() as session:
            soma = func.coalesce(func.sum(RegistroCustoIAModel.custo_usd), Decimal("0"))
            stmt = select(soma).where(
                RegistroCustoIAModel.empresa_id == empresa_id,
                RegistroCustoIAModel.criado_em >= inicio,
                RegistroCustoIAModel.criado_em < fim,
            )
            if conta_ig_id is not None:
                stmt = stmt.where(RegistroCustoIAModel.conta_ig_id == conta_ig_id)
            total = await session.scalar(stmt)
            return Decimal(str(total if total is not None else "0"))

    async def somar_mes_empresa(self, empresa_id: UUID, ano: int, mes: int) -> Decimal:
        return await self._somar_periodo(empresa_id, ano, mes)

    async def somar_mes_por_conta(
        self, empresa_id: UUID, conta_ig_id: UUID, ano: int, mes: int
    ) -> Decimal:
        return await self._somar_periodo(empresa_id, ano, mes, conta_ig_id=conta_ig_id)
