"""Testes unitários do ServicoOAuthMetaUseCase (OAuth one-time, Fernet e refresh)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.aplicacao.publicacao import ConectarMetaCallbackCmd, ServicoOAuthMetaUseCase
from app.core.seguranca.criptografia_fernet import FernetCipher
from app.dominio.excecoes import ErroCredenciaisInvalidas, ErroValidacaoDominio
from app.infra.memoria.repo_conteudo_mem import InMemoryContaIGRepository
from app.infra.meta.state_oauth_store import StateOAuthMemoria


class _FakeAuthMeta:
    def __init__(self) -> None:
        self.codigo_recebido = ""
        self.token_atual = "token_longo_v1"

    def gerar_url_autorizacao(self, state: str) -> str:
        return f"https://www.instagram.com/oauth/authorize?state={state}"

    async def trocar_codigo_por_token(self, codigo: str) -> tuple[str, int, str, str]:
        self.codigo_recebido = codigo
        return self.token_atual, 5184000, "178414001", "@minha_loja"

    async def renovar_token_longo(self, token_atual: str) -> tuple[str, int]:
        assert token_atual == self.token_atual
        return "token_longo_v2", 5184000


async def test_oauth_fluxo_completo_upsert_e_criptografia() -> None:
    repo = InMemoryContaIGRepository()
    auth = _FakeAuthMeta()
    cripto = FernetCipher([Fernet.generate_key().decode("utf-8")])
    store = StateOAuthMemoria()
    uc = ServicoOAuthMetaUseCase(repo, auth, cripto, store)

    empresa_id, usuario_id = uuid4(), uuid4()
    url, state = await uc.iniciar_autorizacao(empresa_id, usuario_id)
    assert state in url

    conta = await uc.concluir_callback(
        ConectarMetaCallbackCmd(
            empresa_id=empresa_id, usuario_id=usuario_id, codigo="cod_123", state=state
        )
    )
    assert conta.ig_user_id == "178414001"
    assert conta.username == "minha_loja"
    assert conta.access_token_enc != "token_longo_v1"
    assert cripto.descriptografar(conta.access_token_enc) == "token_longo_v1"

    # Replay do mesmo state deve falhar
    with pytest.raises(ErroCredenciaisInvalidas):
        await uc.concluir_callback(
            ConectarMetaCallbackCmd(
                empresa_id=empresa_id, usuario_id=usuario_id, codigo="cod_123", state=state
            )
        )

    # Reconexão da mesma conta atualiza sem duplicar registro
    auth.token_atual = "token_longo_reconectado"
    _, state2 = await uc.iniciar_autorizacao(empresa_id, usuario_id)
    conta_upd = await uc.concluir_callback(
        ConectarMetaCallbackCmd(
            empresa_id=empresa_id, usuario_id=usuario_id, codigo="cod_456", state=state2
        )
    )
    assert conta_upd.id == conta.id
    assert len(await repo.listar_por_empresa(empresa_id)) == 1
    assert cripto.descriptografar(conta_upd.access_token_enc) == "token_longo_reconectado"


async def test_oauth_bloqueia_csrf_de_outro_tenant_e_renova_token() -> None:
    repo = InMemoryContaIGRepository()
    auth = _FakeAuthMeta()
    cripto = FernetCipher([Fernet.generate_key().decode("utf-8")])
    store = StateOAuthMemoria()
    uc = ServicoOAuthMetaUseCase(repo, auth, cripto, store)

    empresa_a, user_a = uuid4(), uuid4()
    empresa_b, user_b = uuid4(), uuid4()
    _, state = await uc.iniciar_autorizacao(empresa_a, user_a)

    with pytest.raises(ErroCredenciaisInvalidas):
        await uc.concluir_callback(
            ConectarMetaCallbackCmd(
                empresa_id=empresa_b, usuario_id=user_b, codigo="cod", state=state
            )
        )

    _, state_ok = await uc.iniciar_autorizacao(empresa_a, user_a)
    conta = await uc.concluir_callback(
        ConectarMetaCallbackCmd(
            empresa_id=empresa_a, usuario_id=user_a, codigo="cod", state=state_ok
        )
    )
    conta.token_expira_em = datetime.now(UTC) + timedelta(days=5)
    await repo.salvar(conta)

    renovada = await uc.renovar_token_conta(empresa_a, conta.id)
    assert cripto.descriptografar(renovada.access_token_enc) == "token_longo_v2"
    assert renovada.token_expira_em > datetime.now(UTC) + timedelta(days=50)

    with pytest.raises(ErroValidacaoDominio):
        await uc.renovar_token_conta(empresa_b, conta.id)
