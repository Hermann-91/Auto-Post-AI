"""Repositórios SQLAlchemy Async para mídia, configuração de IA e fontes RAG."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.excecoes import ErroConflitoDados
from app.dominio.objetos_valor.enums_conteudo import PastaMidia
from app.infra.db.modelos_conteudo import MidiaBibliotecaModel


def _para_midia(m: MidiaBibliotecaModel) -> MidiaBiblioteca:
    return MidiaBiblioteca(
        id=m.id,
        empresa_id=m.empresa_id,
        conta_ig_id=m.conta_ig_id,
        pasta=PastaMidia(m.pasta),
        chave_storage=m.chave_storage,
        tipo_arquivo=m.tipo_arquivo,
        tamanho_bytes=m.tamanho_bytes,
        curtida_favorita=m.curtida_favorita,
        resumo_visual=m.resumo_visual,
        criado_em=m.criado_em,
    )


class SqlMidiaRepository:
    """Persistência SQL da biblioteca de mídia isolada por (empresa_id, conta_ig_id)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def salvar(self, midia: MidiaBiblioteca) -> MidiaBiblioteca:
        modelo = MidiaBibliotecaModel(
            id=midia.id,
            empresa_id=midia.empresa_id,
            conta_ig_id=midia.conta_ig_id,
            pasta=midia.pasta.value,
            chave_storage=midia.chave_storage,
            tipo_arquivo=midia.tipo_arquivo,
            tamanho_bytes=midia.tamanho_bytes,
            curtida_favorita=midia.curtida_favorita,
            resumo_visual=midia.resumo_visual,
            criado_em=midia.criado_em,
        )
        try:
            async with self._sf() as session, session.begin():
                await session.merge(modelo)
        except IntegrityError as exc:
            raise ErroConflitoDados("Chave de mídia já registrada no storage.") from exc
        return midia

    async def buscar_por_id(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        midia_id: UUID,
    ) -> MidiaBiblioteca | None:
        async with self._sf() as session:
            stmt = select(MidiaBibliotecaModel).where(
                MidiaBibliotecaModel.id == midia_id,
                MidiaBibliotecaModel.empresa_id == empresa_id,
                MidiaBibliotecaModel.conta_ig_id == conta_ig_id,
            )
            modelo = await session.scalar(stmt)
            return _para_midia(modelo) if modelo is not None else None

    async def listar_por_conta(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        pasta: PastaMidia | None = None,
    ) -> list[MidiaBiblioteca]:
        async with self._sf() as session:
            stmt = select(MidiaBibliotecaModel).where(
                MidiaBibliotecaModel.empresa_id == empresa_id,
                MidiaBibliotecaModel.conta_ig_id == conta_ig_id,
            )
            if pasta is not None:
                stmt = stmt.where(MidiaBibliotecaModel.pasta == pasta.value)
            stmt = stmt.order_by(MidiaBibliotecaModel.criado_em.desc())
            modelos = (await session.scalars(stmt)).all()
            return [_para_midia(m) for m in modelos]

    async def calcular_uso_cota(self, empresa_id: UUID, conta_ig_id: UUID) -> tuple[int, int]:
        async with self._sf() as session:
            stmt = select(
                func.count(MidiaBibliotecaModel.id),
                func.coalesce(func.sum(MidiaBibliotecaModel.tamanho_bytes), 0),
            ).where(
                MidiaBibliotecaModel.empresa_id == empresa_id,
                MidiaBibliotecaModel.conta_ig_id == conta_ig_id,
            )
            linha = (await session.execute(stmt)).one()
            return int(linha[0] or 0), int(linha[1] or 0)

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, midia_id: UUID) -> None:
        async with self._sf() as session, session.begin():
            stmt = delete(MidiaBibliotecaModel).where(
                MidiaBibliotecaModel.id == midia_id,
                MidiaBibliotecaModel.empresa_id == empresa_id,
                MidiaBibliotecaModel.conta_ig_id == conta_ig_id,
            )
            await session.execute(stmt)
