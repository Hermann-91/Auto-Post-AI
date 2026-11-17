"""Testes de integração do ExecutorLotesWorker (concorrência e refresh tokens)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.fernet import Fernet

from app.aplicacao.publicacao import ServicoAgendamentoUseCase, ServicoOAuthMetaUseCase
from app.core.seguranca.criptografia_fernet import FernetCipher
from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem, TipoMidia
from app.dominio.portas.ia_meta import PublicadorMidiaStrategyPort
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryContaIGRepository,
    InMemoryMidiaRepository,
)
from app.infra.memoria.repo_publicacao_mem import InMemoryPostagemRepository
from app.infra.meta.state_oauth_store import StateOAuthMemoria
from app.worker.executor_lotes import ExecutorLotesWorker
from app.worker.locks import LockMemoria


class _FakeStorage:
    async def enviar_bytes(self, chave: str, conteudo: bytes, content_type: str) -> str:
        _ = (conteudo, content_type)
        return f"https://cdn.site/{chave}"

    async def baixar_bytes(self, chave: str) -> bytes:
        _ = chave
        return b""

    async def obter_url_publica(self, chave: str) -> str:
        return f"https://cdn.site/{chave}"

    async def remover_objeto(self, chave: str) -> None:
        _ = chave


class _FakeAuth:
    def gerar_url_autorizacao(self, state: str) -> str:
        return f"https://meta/{state}"

    async def trocar_codigo_por_token(self, codigo: str) -> tuple[str, int, str, str]:
        _ = codigo
        return "t", 100, "1", "u"

    async def renovar_token_longo(self, token_atual: str) -> tuple[str, int]:
        return f"{token_atual}_renovado", 5184000


class _FakePublicadorLento:
    tipo_suportado = TipoMidia.IMAGE

    def __init__(self) -> None:
        self.chamadas = 0

    async def publicar(
        self,
        conta: ContaInstagram,
        token_descriptografado: str,
        postagem: Postagem,
        urls_publicas: list[str],
    ) -> tuple[str, str]:
        _ = (conta, token_descriptografado, postagem, urls_publicas)
        self.chamadas += 1
        await asyncio.sleep(0.02)
        return f"m_{self.chamadas}", f"c_{self.chamadas}"


class _FabricaUnica:
    def __init__(self, est: PublicadorMidiaStrategyPort) -> None:
        self._est = est

    def obter(self, tipo_midia: TipoMidia) -> PublicadorMidiaStrategyPort:
        _ = tipo_midia
        return self._est


async def test_executor_concorrente_sem_duplicacao_e_renovacao_tokens() -> None:
    conta_repo = InMemoryContaIGRepository()
    midia_repo = InMemoryMidiaRepository()
    post_repo = InMemoryPostagemRepository()
    cripto = FernetCipher([Fernet.generate_key().decode("utf-8")])
    lock = LockMemoria()
    pub = _FakePublicadorLento()

    empresa_id = uuid4()
    conta_perto = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=empresa_id,
            ig_user_id="101",
            username="perto",
            access_token_enc=cripto.criptografar("tok_perto"),
            token_expira_em=datetime.now(UTC) + timedelta(days=4),
        )
    )
    conta_longe = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=empresa_id,
            ig_user_id="102",
            username="longe",
            access_token_enc=cripto.criptografar("tok_longe"),
            token_expira_em=datetime.now(UTC) + timedelta(days=45),
        )
    )

    p_vencida = Postagem(
        empresa_id=empresa_id, conta_ig_id=conta_perto.id,
        tipo_midia=TipoMidia.IMAGE, midias_chaves=["foto.jpg"], legenda="Agora",
    )
    p_vencida.agendar(datetime.now(UTC) - timedelta(minutes=1))
    await post_repo.salvar(p_vencida)

    p_futura = Postagem(
        empresa_id=empresa_id, conta_ig_id=conta_perto.id,
        tipo_midia=TipoMidia.IMAGE, midias_chaves=["foto2.jpg"], legenda="Depois",
    )
    p_futura.agendar(datetime.now(UTC) + timedelta(hours=3))
    await post_repo.salvar(p_futura)

    ag_uc = ServicoAgendamentoUseCase(
        conta_repo, midia_repo, post_repo, _FakeStorage(), cripto, _FabricaUnica(pub), lock
    )
    oauth_uc = ServicoOAuthMetaUseCase(conta_repo, _FakeAuth(), cripto, StateOAuthMemoria())
    executor = ExecutorLotesWorker(
        post_repo, conta_repo, ag_uc, oauth_uc, lock, dias_antes_renovar=10
    )

    res1, res2 = await asyncio.gather(
        executor.executar_ciclo_publicacoes(),
        executor.executar_ciclo_publicacoes(),
    )
    assert pub.chamadas == 1
    assert res1.publicadas + res2.publicadas == 1
    assert res1.ignoradas_por_lock + res2.ignoradas_por_lock == 1
    atualizada = await post_repo.buscar_por_id(empresa_id, conta_perto.id, p_vencida.id)
    assert atualizada is not None and atualizada.status == StatusPostagem.PUBLICADO

    res_tok = await executor.executar_ciclo_renovacao_tokens()
    assert res_tok.elegiveis == 1 and res_tok.renovadas == 1
    c_perto = await conta_repo.buscar_por_id(empresa_id, conta_perto.id)
    c_longe = await conta_repo.buscar_por_id(empresa_id, conta_longe.id)
    assert c_perto is not None
    assert cripto.descriptografar(c_perto.access_token_enc) == "tok_perto_renovado"
    assert c_longe is not None
    assert cripto.descriptografar(c_longe.access_token_enc) == "tok_longe"


async def test_worker_recupera_postagem_presa_em_publicando_alem_do_ttl() -> None:
    conta_repo = InMemoryContaIGRepository()
    midia_repo = InMemoryMidiaRepository()
    post_repo = InMemoryPostagemRepository()
    cripto = FernetCipher([Fernet.generate_key().decode("utf-8")])
    lock, pub = LockMemoria(), _FakePublicadorLento()
    emp_id = uuid4()
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp_id, ig_user_id="103", username="travada",
            access_token_enc=cripto.criptografar("tok_trav"),
            token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    agora = datetime(2026, 11, 16, 20, 0, tzinfo=UTC)
    presa = Postagem(
        empresa_id=emp_id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
        midias_chaves=["foto.jpg"], status=StatusPostagem.PUBLICANDO,
        atualizado_em=agora - timedelta(seconds=400),
    )
    esgotada = Postagem(
        empresa_id=emp_id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
        midias_chaves=["foto2.jpg"], status=StatusPostagem.PUBLICANDO,
        tentativas_publicacao=2, atualizado_em=agora - timedelta(seconds=400),
    )
    await post_repo.salvar(presa)
    await post_repo.salvar(esgotada)

    ag_uc = ServicoAgendamentoUseCase(
        conta_repo, midia_repo, post_repo, _FakeStorage(), cripto, _FabricaUnica(pub), lock
    )
    oauth_uc = ServicoOAuthMetaUseCase(conta_repo, _FakeAuth(), cripto, StateOAuthMemoria())
    executor = ExecutorLotesWorker(
        post_repo, conta_repo, ag_uc, oauth_uc, lock, lock_ttl_segundos=300
    )
    res = await executor.executar_ciclo_publicacoes(agora=agora)
    assert res.recuperadas_travadas == 2 and res.publicadas == 1 and pub.chamadas == 1
    p1 = await post_repo.buscar_por_id(emp_id, conta.id, presa.id)
    p2 = await post_repo.buscar_por_id(emp_id, conta.id, esgotada.id)
    assert p1 is not None and p1.status == StatusPostagem.PUBLICADO
    assert p2 is not None and p2.status == StatusPostagem.FALHA
