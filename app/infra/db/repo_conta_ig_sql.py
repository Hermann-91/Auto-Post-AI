"""Repositório SQLAlchemy Async para contas Instagram multi-tenant."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.objetos_valor.enums_tenant import ProvedorMeta
from app.infra.db.modelos_tenant import ContaInstagramModel
from app.infra.db.repo_tenant_sql import _upsert


def _para_conta_ig(m: ContaInstagramModel) -> ContaInstagram:
    return ContaInstagram(
        id=m.id,
        empresa_id=m.empresa_id,
        ig_user_id=m.ig_user_id,
        username=m.username,
        access_token_enc=m.access_token_enc,
        token_expira_em=m.token_expira_em,
        provedor=ProvedorMeta(m.provedor),
        ativa=m.ativa,
        criado_em=m.criado_em,
    )


class SqlContaIGRepository:
    """Persistência SQL multi-conta Instagram isolada por empresa_id."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def salvar(self, conta: ContaInstagram) -> ContaInstagram:
        modelo = ContaInstagramModel(
            id=conta.id,
            empresa_id=conta.empresa_id,
            ig_user_id=conta.ig_user_id,
            username=conta.username,
            access_token_enc=conta.access_token_enc,
            token_expira_em=conta.token_expira_em,
            provedor=conta.provedor.value,
            ativa=conta.ativa,
            criado_em=conta.criado_em,
        )
        await _upsert(self._sf, modelo, "Conta Instagram já vinculada a esta empresa.")
        return conta

    async def buscar_por_id(self, empresa_id: UUID, conta_ig_id: UUID) -> ContaInstagram | None:
        async with self._sf() as session:
            stmt = select(ContaInstagramModel).where(
                ContaInstagramModel.id == conta_ig_id,
                ContaInstagramModel.empresa_id == empresa_id,
            )
            modelo = await session.scalar(stmt)
            return _para_conta_ig(modelo) if modelo is not None else None

    async def listar_por_empresa(self, empresa_id: UUID) -> list[ContaInstagram]:
        async with self._sf() as session:
            stmt = (
                select(ContaInstagramModel)
                .where(ContaInstagramModel.empresa_id == empresa_id)
                .order_by(ContaInstagramModel.criado_em.asc())
            )
            modelos = (await session.scalars(stmt)).all()
            return [_para_conta_ig(m) for m in modelos]

    async def buscar_por_ig_user_id(
        self,
        empresa_id: UUID,
        ig_user_id: str,
    ) -> ContaInstagram | None:
        async with self._sf() as session:
            stmt = select(ContaInstagramModel).where(
                ContaInstagramModel.empresa_id == empresa_id,
                ContaInstagramModel.ig_user_id == ig_user_id.strip(),
            )
            modelo = await session.scalar(stmt)
            return _para_conta_ig(modelo) if modelo is not None else None

    async def listar_para_renovacao_token(self, expira_antes: datetime) -> list[ContaInstagram]:
        async with self._sf() as session:
            stmt = (
                select(ContaInstagramModel)
                .where(
                    ContaInstagramModel.ativa.is_(True),
                    ContaInstagramModel.token_expira_em <= expira_antes,
                )
                .order_by(ContaInstagramModel.token_expira_em.asc())
            )
            modelos = (await session.scalars(stmt)).all()
            return [_para_conta_ig(m) for m in modelos]
