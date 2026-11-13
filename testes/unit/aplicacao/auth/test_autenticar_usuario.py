"""Testes unitários de AutenticarUsuarioUseCase."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.aplicacao.auth import AutenticarUsuarioUseCase, LoginCmd
from app.aplicacao.auth.emissao_sessao import EmissorSessaoAuth
from app.aplicacao.auth.protecao_entrada import GuardiaoEntradaAuth
from app.core.seguranca.senha_argon2 import Argon2idHasher
from app.core.seguranca.token_jwt import JwtTokenService
from app.dominio.entidades.tenant import Usuario
from app.dominio.excecoes import ErroCaptchaInvalido, ErroCredenciaisInvalidas
from app.infra.memoria import InMemoryRefreshTokenRepository, InMemoryUsuarioRepository
from app.infra.seguranca import InMemoryRateLimiter, StubCaptchaAdapter


class _SpyHasher:
    def __init__(self, real: Argon2idHasher) -> None:
        self._real = real
        self.chamadas_verificar = 0
        self.chamadas_dummy = 0

    async def gerar_hash(self, senha_plana: str) -> str:
        return await self._real.gerar_hash(senha_plana)

    async def verificar(self, senha_plana: str, senha_hash: str) -> bool:
        self.chamadas_verificar += 1
        return await self._real.verificar(senha_plana, senha_hash)

    async def verificar_dummy(self, senha_plana: str) -> None:
        self.chamadas_dummy += 1
        await self._real.verificar_dummy(senha_plana)


async def test_captcha_invalido_bloqueia_antes_do_argon2(hasher_rapido: Argon2idHasher) -> None:
    spy_hasher = _SpyHasher(hasher_rapido)
    uc = AutenticarUsuarioUseCase(
        usuario_repo=InMemoryUsuarioRepository(),
        hasher=spy_hasher,
        guardiao=GuardiaoEntradaAuth(InMemoryRateLimiter(), StubCaptchaAdapter(False)),
        emissor=EmissorSessaoAuth(JwtTokenService("k" * 32), InMemoryRefreshTokenRepository()),
    )

    with pytest.raises(ErroCaptchaInvalido):
        await uc.executar(LoginCmd("x@y.com", "senha", "bad-captcha", "10.0.0.1"))
    assert spy_hasher.chamadas_verificar == 0
    assert spy_hasher.chamadas_dummy == 0


async def test_email_inexistente_executa_dummy_e_retorna_mensagem_generica(
    hasher_rapido: Argon2idHasher,
) -> None:
    spy_hasher = _SpyHasher(hasher_rapido)
    repo = InMemoryUsuarioRepository()

    await repo.salvar(
        Usuario(
            empresa_id=uuid4(),
            email="real@empresa.com",
            senha_hash=await hasher_rapido.gerar_hash("Correta123"),
        )
    )
    uc = AutenticarUsuarioUseCase(
        usuario_repo=repo,
        hasher=spy_hasher,
        guardiao=GuardiaoEntradaAuth(InMemoryRateLimiter(), StubCaptchaAdapter(True)),
        emissor=EmissorSessaoAuth(JwtTokenService("k" * 32), InMemoryRefreshTokenRepository()),
    )

    with pytest.raises(ErroCredenciaisInvalidas) as exc_inexistente:
        await uc.executar(LoginCmd("naoexiste@empresa.com", "Correta123", "ok", "10.0.0.1"))
    assert spy_hasher.chamadas_dummy == 1

    with pytest.raises(ErroCredenciaisInvalidas) as exc_senha:
        await uc.executar(LoginCmd("real@empresa.com", "Errada", "ok", "10.0.0.1"))
    assert str(exc_inexistente.value) == str(exc_senha.value)
