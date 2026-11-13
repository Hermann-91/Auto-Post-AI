"""Caso de uso de autenticação com ordem rígida de proteção de entrada."""

from __future__ import annotations

from app.aplicacao.auth.dtos import LoginCmd, ParTokensDTO
from app.aplicacao.auth.emissao_sessao import EmissorSessaoAuth
from app.aplicacao.auth.protecao_entrada import GuardiaoEntradaAuth
from app.dominio.excecoes import ErroCredenciaisInvalidas
from app.dominio.portas.repositorios_tenant import UsuarioRepositoryPort
from app.dominio.portas.seguranca import HasherSenhaPort

_MSG_CREDENCIAIS_INVALIDAS = "E-mail ou senha inválidos."


class AutenticarUsuarioUseCase:
    """Autentica usuário multi-tenant mitigando brute force e timing attacks."""

    def __init__(
        self,
        usuario_repo: UsuarioRepositoryPort,
        hasher: HasherSenhaPort,
        guardiao: GuardiaoEntradaAuth,
        emissor: EmissorSessaoAuth,
    ) -> None:
        self._usuario_repo = usuario_repo
        self._hasher = hasher
        self._guardiao = guardiao
        self._emissor = emissor

    async def executar(self, cmd: LoginCmd) -> ParTokensDTO:
        """Executa Rate Limit -> Turnstile -> Argon2id -> emissão de sessão."""
        await self._guardiao.validar_entrada(
            email=cmd.email,
            token_captcha=cmd.token_captcha,
            ip_remoto=cmd.ip_remoto,
            escopo="login",
        )

        email_norm = cmd.email.strip().lower()
        usuario = await self._usuario_repo.buscar_por_email(email_norm)
        if usuario is None:
            await self._hasher.verificar_dummy(cmd.senha)
            raise ErroCredenciaisInvalidas(_MSG_CREDENCIAIS_INVALIDAS)

        senha_valida = await self._hasher.verificar(cmd.senha, usuario.senha_hash)
        if not senha_valida or not usuario.ativo:
            raise ErroCredenciaisInvalidas(_MSG_CREDENCIAIS_INVALIDAS)

        tokens, _ = await self._emissor.emitir_sessao(usuario)
        return tokens
