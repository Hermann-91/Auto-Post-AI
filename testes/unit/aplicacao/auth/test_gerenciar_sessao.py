"""Testes unitários de RenovarSessaoUseCase e EncerrarSessaoUseCase."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.aplicacao.auth import EncerrarSessaoUseCase, RenovarSessaoUseCase
from app.aplicacao.auth.emissao_sessao import EmissorSessaoAuth
from app.core.seguranca.token_jwt import JwtTokenService
from app.dominio.entidades.tenant import Usuario
from app.dominio.excecoes import ErroCredenciaisInvalidas, ErroTokenReutilizado
from app.infra.memoria import InMemoryRefreshTokenRepository, InMemoryUsuarioRepository


async def test_rotacao_e_deteccao_de_reuso_revoga_toda_familia() -> None:
    tokens = JwtTokenService("k" * 32)
    refresh_repo = InMemoryRefreshTokenRepository()
    usuario_repo = InMemoryUsuarioRepository()
    usuario = Usuario(empresa_id=uuid4(), email="u@emp.com", senha_hash="hash")
    await usuario_repo.salvar(usuario)

    emissor = EmissorSessaoAuth(tokens, refresh_repo)
    par1, _ = await emissor.emitir_sessao(usuario)

    renovar = RenovarSessaoUseCase(tokens, refresh_repo, usuario_repo, emissor)
    par2 = await renovar.executar(par1.refresh_token)
    assert par2.refresh_token != par1.refresh_token

    # Reuso do token antigo par1 deve disparar ErroTokenReutilizado e matar par2 também
    with pytest.raises(ErroTokenReutilizado):
        await renovar.executar(par1.refresh_token)

    with pytest.raises(ErroTokenReutilizado):
        await renovar.executar(par2.refresh_token)


async def test_logout_revoga_familia_do_refresh_token() -> None:
    tokens = JwtTokenService("k" * 32)
    refresh_repo = InMemoryRefreshTokenRepository()
    usuario_repo = InMemoryUsuarioRepository()
    usuario = Usuario(empresa_id=uuid4(), email="u@emp.com", senha_hash="hash")
    await usuario_repo.salvar(usuario)

    emissor = EmissorSessaoAuth(tokens, refresh_repo)
    par, _ = await emissor.emitir_sessao(usuario)

    encerrar = EncerrarSessaoUseCase(tokens, refresh_repo)
    await encerrar.executar(par.refresh_token)

    renovar = RenovarSessaoUseCase(tokens, refresh_repo, usuario_repo, emissor)
    with pytest.raises(ErroTokenReutilizado):
        await renovar.executar(par.refresh_token)

    with pytest.raises(ErroCredenciaisInvalidas):
        await renovar.executar(None)
