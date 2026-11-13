"""Caso de uso para cadastro de nova empresa e usuário administrador."""

from __future__ import annotations

from app.aplicacao.auth.dtos import ParTokensDTO, RegistroUsuarioCmd
from app.aplicacao.auth.emissao_sessao import EmissorSessaoAuth
from app.aplicacao.auth.protecao_entrada import GuardiaoEntradaAuth
from app.dominio.entidades.tenant import Empresa, Usuario
from app.dominio.excecoes import ErroConflitoDados, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_tenant import PapelUsuario
from app.dominio.portas.repositorios_tenant import (
    EmpresaRepositoryPort,
    UsuarioRepositoryPort,
)
from app.dominio.portas.seguranca import HasherSenhaPort


class RegistrarUsuarioUseCase:
    """Cria nova Empresa e seu primeiro usuário ADMIN sem confiar em tenant externo."""

    def __init__(
        self,
        empresa_repo: EmpresaRepositoryPort,
        usuario_repo: UsuarioRepositoryPort,
        hasher: HasherSenhaPort,
        guardiao: GuardiaoEntradaAuth,
        emissor: EmissorSessaoAuth,
    ) -> None:
        self._empresa_repo = empresa_repo
        self._usuario_repo = usuario_repo
        self._hasher = hasher
        self._guardiao = guardiao
        self._emissor = emissor

    async def executar(self, cmd: RegistroUsuarioCmd) -> ParTokensDTO:
        """Valida entrada anti-bot, cria tenant/usuário e retorna sessão inicial."""
        await self._guardiao.validar_entrada(
            email=cmd.email,
            token_captcha=cmd.token_captcha,
            ip_remoto=cmd.ip_remoto,
            escopo="register",
        )
        if len(cmd.senha) < 8:
            raise ErroValidacaoDominio("A senha deve conter ao menos 8 caracteres.")

        email_norm = cmd.email.strip().lower()
        existente = await self._usuario_repo.buscar_por_email(email_norm)
        if existente is not None:
            raise ErroConflitoDados("Não foi possível concluir o cadastro com este e-mail.")

        empresa = Empresa(nome=cmd.nome_empresa)
        senha_hash = await self._hasher.gerar_hash(cmd.senha)
        usuario = Usuario(
            empresa_id=empresa.id,
            email=email_norm,
            senha_hash=senha_hash,
            papel=PapelUsuario.ADMIN,
        )

        await self._empresa_repo.salvar(empresa)
        await self._usuario_repo.salvar(usuario)

        tokens, _ = await self._emissor.emitir_sessao(usuario)
        return tokens
