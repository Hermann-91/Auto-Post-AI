"""Testes unitários de RegistrarUsuarioUseCase."""

from __future__ import annotations

import pytest

from app.aplicacao.auth import RegistrarUsuarioUseCase, RegistroUsuarioCmd
from app.aplicacao.auth.emissao_sessao import EmissorSessaoAuth
from app.aplicacao.auth.protecao_entrada import GuardiaoEntradaAuth
from app.core.seguranca.senha_argon2 import Argon2idHasher
from app.core.seguranca.token_jwt import JwtTokenService
from app.dominio.excecoes import ErroConflitoDados, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_tenant import PapelUsuario
from app.infra.memoria import (
    InMemoryEmpresaRepository,
    InMemoryRefreshTokenRepository,
    InMemoryUsuarioRepository,
)
from app.infra.seguranca import InMemoryRateLimiter, StubCaptchaAdapter


def _criar_uc(hasher_rapido: Argon2idHasher) -> RegistrarUsuarioUseCase:
    tokens = JwtTokenService("segredo-teste-32-caracteres-valido")
    return RegistrarUsuarioUseCase(
        empresa_repo=InMemoryEmpresaRepository(),
        usuario_repo=InMemoryUsuarioRepository(),
        hasher=hasher_rapido,
        guardiao=GuardiaoEntradaAuth(InMemoryRateLimiter(), StubCaptchaAdapter(True)),
        emissor=EmissorSessaoAuth(tokens, InMemoryRefreshTokenRepository()),
    )


async def test_registrar_cria_empresa_usuario_admin_e_bloqueia_duplicado(
    hasher_rapido: Argon2idHasher,
) -> None:
    uc = _criar_uc(hasher_rapido)
    par = await uc.executar(
        RegistroUsuarioCmd("Loja Alpha", "dono@alpha.com", "SenhaForte123", "ok", "127.0.0.1")
    )

    assert par.usuario.papel == PapelUsuario.ADMIN
    assert par.access_token and par.refresh_token

    with pytest.raises(ErroConflitoDados):
        await uc.executar(
            RegistroUsuarioCmd("Outra", "dono@alpha.com", "SenhaForte123", "ok", "127.0.0.1")
        )


async def test_registrar_rejeita_senha_curta(hasher_rapido: Argon2idHasher) -> None:
    uc = _criar_uc(hasher_rapido)
    with pytest.raises(ErroValidacaoDominio):
        await uc.executar(
            RegistroUsuarioCmd("Loja Beta", "a@beta.com", "123", "ok", "127.0.0.1")
        )
