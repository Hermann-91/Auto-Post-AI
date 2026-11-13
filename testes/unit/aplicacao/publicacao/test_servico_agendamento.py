"""Testes unitários de ServicoAgendamentoUseCase (anti-IDOR, cota e estados)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.aplicacao.publicacao import (
    AgendarPostagemCmd,
    CriarPostagemCmd,
    ServicoAgendamentoUseCase,
)
from app.core.seguranca.criptografia_fernet import FernetCipher
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import (
    ErroIntegracaoMeta,
    ErroLimitePublicacaoMeta,
    ErroTransicaoEstado,
    ErroValidacaoDominio,
)
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, StatusPostagem, TipoMidia
from app.dominio.portas.ia_meta import PublicadorMidiaStrategyPort
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryContaIGRepository,
    InMemoryMidiaRepository,
)
from app.infra.memoria.repo_publicacao_mem import InMemoryPostagemRepository
from app.worker.locks import LockMemoria


class _FakeStorageUrl:
    async def enviar_bytes(self, chave: str, conteudo: bytes, content_type: str) -> str:
        _ = (conteudo, content_type)
        return f"https://cdn.exemplo.com/{chave}"

    async def baixar_bytes(self, chave: str) -> bytes:
        _ = chave
        return b"bytes"

    async def obter_url_publica(self, chave: str) -> str:
        return f"https://cdn.exemplo.com/{chave}"

    async def remover_objeto(self, chave: str) -> None:
        _ = chave


class _FakeEstrategiaMeta:
    tipo_suportado = TipoMidia.IMAGE

    def __init__(self, erro: Exception | None = None) -> None:
        self._erro = erro

    async def publicar(
        self,
        conta: ContaInstagram,
        token_descriptografado: str,
        postagem: Postagem,
        urls_publicas: list[str],
    ) -> tuple[str, str]:
        _ = (conta, postagem, urls_publicas)
        assert token_descriptografado == "tok_meta_secreto"
        if self._erro is not None:
            raise self._erro
        return "media_999", "cont_888"


class _FakeFabricaMeta:
    def __init__(self, estrategia: PublicadorMidiaStrategyPort) -> None:
        self._est = estrategia

    def obter(self, tipo_midia: TipoMidia) -> PublicadorMidiaStrategyPort:
        return self._est


async def _setup_base(
    erro: Exception | None = None,
) -> tuple[
    ServicoAgendamentoUseCase,
    ContaInstagram,
    MidiaBiblioteca,
    InMemoryMidiaRepository,
    LockMemoria,
]:
    c_repo, m_repo, p_repo = (
        InMemoryContaIGRepository(),
        InMemoryMidiaRepository(),
        InMemoryPostagemRepository(),
    )
    cripto = FernetCipher([Fernet.generate_key().decode("utf-8")])
    lock, emp_id = LockMemoria(), uuid4()
    conta = await c_repo.salvar(ContaInstagram(
        empresa_id=emp_id, ig_user_id="17841", username="perfil_teste",
        access_token_enc=cripto.criptografar("tok_meta_secreto"),
        token_expira_em=datetime.now(UTC) + timedelta(days=30),
    ))
    midia = await m_repo.salvar(MidiaBiblioteca(
        empresa_id=emp_id, conta_ig_id=conta.id, pasta=PastaMidia.IA_CRIA,
        chave_storage=f"{emp_id}/{conta.id}/IA-Cria/foto.jpg",
        tipo_arquivo="image/jpeg", tamanho_bytes=1200,
    ))
    uc = ServicoAgendamentoUseCase(
        conta_repo=c_repo, midia_repo=m_repo, post_repo=p_repo,
        storage=_FakeStorageUrl(), cripto=cripto,
        fabrica_publicadores=_FakeFabricaMeta(_FakeEstrategiaMeta(erro)),
        lock_distribuido=lock,
    )
    return uc, conta, midia, m_repo, lock


async def test_criar_previne_idor_e_publica_com_sucesso() -> None:
    uc, conta, midia, midia_repo, _ = await _setup_base()
    midia_alheia = await midia_repo.salvar(MidiaBiblioteca(
        empresa_id=uuid4(), conta_ig_id=uuid4(), pasta=PastaMidia.ORIGINAIS,
        chave_storage="outro/t/f.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=500,
    ))
    with pytest.raises(ErroValidacaoDominio):
        await uc.criar_postagem(CriarPostagemCmd(
            empresa_id=conta.empresa_id, conta_ig_id=conta.id,
            tipo_midia=TipoMidia.IMAGE, midia_ids=(midia_alheia.id,),
        ))
    post = await uc.criar_postagem(CriarPostagemCmd(
        empresa_id=conta.empresa_id, conta_ig_id=conta.id,
        tipo_midia=TipoMidia.IMAGE, midia_ids=(midia.id,), legenda="Lançamento!",
    ))
    with pytest.raises(ErroValidacaoDominio):
        await uc.agendar_postagem(AgendarPostagemCmd(
            empresa_id=conta.empresa_id, conta_ig_id=conta.id,
            postagem_id=post.id, agendado_para=datetime(2026, 11, 20, 12, 0),
        ))
    agendada = await uc.agendar_postagem(AgendarPostagemCmd(
        empresa_id=conta.empresa_id, conta_ig_id=conta.id,
        postagem_id=post.id, agendado_para=datetime.now(UTC) + timedelta(minutes=10),
    ))
    assert agendada.status == StatusPostagem.AGENDADO

    res = await uc.publicar_postagem(conta.empresa_id, conta.id, post.id)
    assert res.publicada is True
    assert res.postagem.status == StatusPostagem.PUBLICADO
    assert res.postagem.meta_media_id == "media_999"
    assert res.postagem.meta_container_id == "cont_888"

    with pytest.raises(ErroTransicaoEstado):
        await uc.cancelar_postagem(conta.empresa_id, conta.id, post.id)


async def test_reagenda_em_cota_meta_falha_e_respeita_lock() -> None:
    uc_cota, conta1, midia1, _, _ = await _setup_base(ErroLimitePublicacaoMeta("Cota 50/50"))
    post1 = await uc_cota.criar_postagem(CriarPostagemCmd(
        empresa_id=conta1.empresa_id, conta_ig_id=conta1.id,
        tipo_midia=TipoMidia.IMAGE, midia_ids=(midia1.id,), agendado_para=datetime.now(UTC),
    ))
    res_cota = await uc_cota.publicar_postagem(conta1.empresa_id, conta1.id, post1.id)
    assert res_cota.publicada is False and res_cota.reagendada is True
    assert res_cota.postagem.status == StatusPostagem.AGENDADO
    assert res_cota.postagem.agendado_para is not None
    assert res_cota.postagem.agendado_para > datetime.now(UTC) + timedelta(minutes=30)

    uc_err, conta2, midia2, _, lock2 = await _setup_base(ErroIntegracaoMeta("Container ERROR"))
    post2 = await uc_err.criar_postagem(CriarPostagemCmd(
        empresa_id=conta2.empresa_id, conta_ig_id=conta2.id,
        tipo_midia=TipoMidia.IMAGE, midia_ids=(midia2.id,), agendado_para=datetime.now(UTC),
    ))
    tok = await lock2.adquirir(f"post:{post2.id}", 60)
    assert tok is not None
    res_lock = await uc_err.publicar_postagem(conta2.empresa_id, conta2.id, post2.id)
    assert res_lock.publicada is False and "outro worker" in res_lock.motivo
    await lock2.liberar(f"post:{post2.id}", tok)

    res_err = await uc_err.publicar_postagem(conta2.empresa_id, conta2.id, post2.id)
    assert res_err.publicada is False and res_err.postagem.status == StatusPostagem.FALHA
    assert "Container ERROR" in (res_err.postagem.erro_detalhe or "")
