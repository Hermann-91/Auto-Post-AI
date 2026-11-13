"""Repositórios SQLAlchemy Async para empresas, usuários, refresh tokens e contas IG."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dominio.entidades.tenant import (
    Empresa,
    RefreshTokenRegistro,
    Usuario,
)
from app.dominio.excecoes import ErroConflitoDados
from app.dominio.objetos_valor.enums_tenant import PapelUsuario, PlanoEmpresa
from app.infra.db.modelos_tenant import (
    EmpresaModel,
    RefreshTokenModel,
    UsuarioModel,
)
from app.infra.db.sessao import Base


async def _upsert(sf: async_sessionmaker[AsyncSession], modelo: Base, erro_conflito: str) -> None:
    try:
        async with sf() as session, session.begin():
            await session.merge(modelo)
    except IntegrityError as exc:
        raise ErroConflitoDados(erro_conflito) from exc


def _para_empresa(m: EmpresaModel) -> Empresa:
    return Empresa(
        id=m.id,
        nome=m.nome,
        plano=PlanoEmpresa(m.plano),
        limite_mensal_usd=m.limite_mensal_usd,
        bloqueio_orcamento=m.bloqueio_orcamento,
        criado_em=m.criado_em,
    )


def _para_usuario(m: UsuarioModel) -> Usuario:
    return Usuario(
        id=m.id,
        empresa_id=m.empresa_id,
        email=m.email,
        senha_hash=m.senha_hash,
        papel=PapelUsuario(m.papel),
        ativo=m.ativo,
        criado_em=m.criado_em,
    )


def _para_refresh(m: RefreshTokenModel) -> RefreshTokenRegistro:
    return RefreshTokenRegistro(
        id=m.id,
        usuario_id=m.usuario_id,
        empresa_id=m.empresa_id,
        familia_id=m.familia_id,
        token_hash=m.token_hash,
        substituido_por=m.substituido_por,
        revogado=m.revogado,
        expira_em=m.expira_em,
        criado_em=m.criado_em,
    )


class SqlEmpresaRepository:
    """Persistência SQL de Empresa."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def salvar(self, empresa: Empresa) -> Empresa:
        modelo = EmpresaModel(
            id=empresa.id,
            nome=empresa.nome,
            plano=empresa.plano.value,
            limite_mensal_usd=empresa.limite_mensal_usd,
            bloqueio_orcamento=empresa.bloqueio_orcamento,
            criado_em=empresa.criado_em,
        )
        await _upsert(self._sf, modelo, "Conflito ao salvar empresa.")
        return empresa

    async def buscar_por_id(self, empresa_id: UUID) -> Empresa | None:
        async with self._sf() as session:
            modelo = await session.get(EmpresaModel, empresa_id)
            return _para_empresa(modelo) if modelo is not None else None


class SqlUsuarioRepository:
    """Persistência SQL de Usuario com índice único de e-mail e isolamento por empresa."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def salvar(self, usuario: Usuario) -> Usuario:
        modelo = UsuarioModel(
            id=usuario.id,
            empresa_id=usuario.empresa_id,
            email=usuario.email,
            senha_hash=usuario.senha_hash,
            papel=usuario.papel.value,
            ativo=usuario.ativo,
            criado_em=usuario.criado_em,
        )
        await _upsert(self._sf, modelo, "Não foi possível concluir o cadastro com este e-mail.")
        return usuario

    async def buscar_por_email(self, email: str) -> Usuario | None:
        email_norm = email.strip().lower()
        async with self._sf() as session:
            stmt = select(UsuarioModel).where(UsuarioModel.email == email_norm)
            modelo = await session.scalar(stmt)
            return _para_usuario(modelo) if modelo is not None else None

    async def buscar_por_id(self, empresa_id: UUID, usuario_id: UUID) -> Usuario | None:
        async with self._sf() as session:
            stmt = select(UsuarioModel).where(
                UsuarioModel.id == usuario_id,
                UsuarioModel.empresa_id == empresa_id,
            )
            modelo = await session.scalar(stmt)
            return _para_usuario(modelo) if modelo is not None else None


class SqlRefreshTokenRepository:
    """Persistência SQL de estado, rotação e revogação por família de Refresh Tokens."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def salvar(self, registro: RefreshTokenRegistro) -> RefreshTokenRegistro:
        modelo = RefreshTokenModel(
            id=registro.id,
            usuario_id=registro.usuario_id,
            empresa_id=registro.empresa_id,
            familia_id=registro.familia_id,
            token_hash=registro.token_hash,
            substituido_por=registro.substituido_por,
            revogado=registro.revogado,
            expira_em=registro.expira_em,
            criado_em=registro.criado_em,
        )
        await _upsert(self._sf, modelo, "Refresh token duplicado.")
        return registro

    async def buscar_por_hash(self, token_hash: str) -> RefreshTokenRegistro | None:
        async with self._sf() as session:
            stmt = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
            modelo = await session.scalar(stmt)
            return _para_refresh(modelo) if modelo is not None else None

    async def marcar_substituido(self, token_id: UUID, novo_id: UUID) -> None:
        async with self._sf() as session, session.begin():
            stmt = (
                update(RefreshTokenModel)
                .where(RefreshTokenModel.id == token_id)
                .values(substituido_por=novo_id)
            )
            await session.execute(stmt)

    async def revogar_familia(self, familia_id: UUID) -> None:
        async with self._sf() as session, session.begin():
            stmt = (
                update(RefreshTokenModel)
                .where(RefreshTokenModel.familia_id == familia_id)
                .values(revogado=True)
            )
            await session.execute(stmt)
