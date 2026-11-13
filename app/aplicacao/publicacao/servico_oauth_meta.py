"""Casos de uso OAuth Meta (Instagram Login) e gestão segura de tokens."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.aplicacao.publicacao.dtos import ConectarMetaCallbackCmd
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroCredenciaisInvalidas, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_tenant import ProvedorMeta
from app.dominio.portas.ia_meta import ProvedorAuthMetaPort
from app.dominio.portas.repositorios_tenant import ContaIGRepositoryPort
from app.dominio.portas.seguranca import CriptografiaPort


class StateOAuthStorePort(Protocol):
    """Porta para armazenamento efêmero de states anti-CSRF OAuth."""

    async def salvar_state(
        self,
        state: str,
        empresa_id: UUID,
        usuario_id: UUID,
        ttl_segundos: int = 600,
    ) -> None: ...
    async def consumir_state(self, state: str) -> tuple[UUID, UUID] | None: ...


class ServicoOAuthMetaUseCase:
    """Orquestra autorização, callback one-time, criptografia Fernet e refresh Meta."""

    def __init__(
        self,
        conta_repo: ContaIGRepositoryPort,
        auth_meta: ProvedorAuthMetaPort,
        cripto: CriptografiaPort,
        state_store: StateOAuthStorePort,
        ttl_state_segundos: int = 600,
    ) -> None:
        self._conta_repo = conta_repo
        self._auth_meta = auth_meta
        self._cripto = cripto
        self._state_store = state_store
        self._ttl_state = ttl_state_segundos

    async def iniciar_autorizacao(self, empresa_id: UUID, usuario_id: UUID) -> tuple[str, str]:
        """Gera state aleatório vinculado ao usuário/empresa e devolve (url, state)."""
        state = secrets.token_urlsafe(32)
        await self._state_store.salvar_state(
            state, empresa_id, usuario_id, ttl_segundos=self._ttl_state
        )
        url = self._auth_meta.gerar_url_autorizacao(state)
        return url, state

    async def concluir_callback(self, cmd: ConectarMetaCallbackCmd) -> ContaInstagram:
        """Valida state da sessão, troca code por Long-Lived Token e persiste conta."""
        state_limpo = cmd.state.strip()
        if not state_limpo or not cmd.codigo.strip():
            raise ErroValidacaoDominio("Parâmetros code e state são obrigatórios no callback.")

        dono = await self._state_store.consumir_state(state_limpo)
        if dono is None or dono != (cmd.empresa_id, cmd.usuario_id):
            raise ErroCredenciaisInvalidas(
                "Estado OAuth Meta inválido, expirado ou pertencente a outra sessão."
            )

        token_longo, expires_in, ig_user_id, username = (
            await self._auth_meta.trocar_codigo_por_token(cmd.codigo)
        )
        token_enc = self._cripto.criptografar(token_longo)
        expira_em = datetime.now(UTC) + timedelta(seconds=expires_in)

        existente = await self._conta_repo.buscar_por_ig_user_id(cmd.empresa_id, ig_user_id)
        if existente is not None:
            existente.username = username.strip().lstrip("@")
            existente.provedor = ProvedorMeta.INSTAGRAM_LOGIN
            existente.ativa = True
            existente.atualizar_token(token_enc, expira_em)
            return await self._conta_repo.salvar(existente)

        nova = ContaInstagram(
            empresa_id=cmd.empresa_id,
            ig_user_id=ig_user_id,
            username=username,
            access_token_enc=token_enc,
            token_expira_em=expira_em,
            provedor=ProvedorMeta.INSTAGRAM_LOGIN,
            ativa=True,
        )
        return await self._conta_repo.salvar(nova)

    async def renovar_token_conta(self, empresa_id: UUID, conta_ig_id: UUID) -> ContaInstagram:
        """Renova o Long-Lived Token da conta e atualiza o segredo criptografado."""
        conta = await self._conta_repo.buscar_por_id(empresa_id, conta_ig_id)
        if conta is None:
            raise ErroValidacaoDominio("Conta Instagram não encontrada para esta empresa.")
        if not conta.ativa:
            raise ErroValidacaoDominio("Conta Instagram está desativada.")

        token_atual = self._cripto.descriptografar(conta.access_token_enc)
        novo_token, expires_in = await self._auth_meta.renovar_token_longo(token_atual)
        novo_enc = self._cripto.criptografar(novo_token)
        nova_expiracao = datetime.now(UTC) + timedelta(seconds=expires_in)
        conta.atualizar_token(novo_enc, nova_expiracao)
        return await self._conta_repo.salvar(conta)
