"""Testes unitários da Fase 3 para rascunho só-texto e retry com backoff Meta."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.aplicacao.publicacao import (
    AgendarPostagemCmd,
    AnexarMidiasPostagemCmd,
    CriarPostagemCmd,
    ServicoAgendamentoUseCase,
)
from app.core.seguranca.criptografia_fernet import FernetCipher
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, StatusPostagem, TipoMidia
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryContaIGRepository,
    InMemoryMidiaRepository,
)
from app.infra.memoria.repo_publicacao_mem import InMemoryPostagemRepository
from app.infra.meta.modelos_meta import ErroHttpMeta, ErroTransitorioMeta
from app.worker.locks import LockMemoria


class _FakeStorageSimples:
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


class _EstrategiaErroSeq:
    tipo_suportado = TipoMidia.IMAGE

    def __init__(self, erros: list[Exception]) -> None:
        self._erros = erros
        self.chamadas = 0

    async def publicar(
        self, conta: ContaInstagram, token: str, postagem: Postagem, urls: list[str]
    ) -> tuple[str, str]:
        _ = (conta, token, postagem, urls)
        self.chamadas += 1
        if self.chamadas <= len(self._erros):
            raise self._erros[self.chamadas - 1]
        return "media_ok", "cont_ok"


class _FabricaSeq:
    def __init__(self, est: _EstrategiaErroSeq) -> None:
        self._est = est

    def obter(self, tipo_midia: TipoMidia) -> _EstrategiaErroSeq:
        _ = tipo_midia
        return self._est


async def _preparar_uc(
    erros: list[Exception], relogio_fixo: datetime
) -> tuple[ServicoAgendamentoUseCase, ContaInstagram, MidiaBiblioteca, InMemoryPostagemRepository]:
    c_repo, m_repo, p_repo = (
        InMemoryContaIGRepository(),
        InMemoryMidiaRepository(),
        InMemoryPostagemRepository(),
    )
    cripto = FernetCipher([Fernet.generate_key().decode("utf-8")])
    emp_id = uuid4()
    conta = await c_repo.salvar(
        ContaInstagram(
            empresa_id=emp_id, ig_user_id="500", username="resiliente",
            access_token_enc=cripto.criptografar("tok_500"),
            token_expira_em=relogio_fixo + timedelta(days=30),
        )
    )
    midia = await m_repo.salvar(
        MidiaBiblioteca(
            empresa_id=emp_id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
            chave_storage=f"{emp_id}/{conta.id}/originais/foto.jpg",
            tipo_arquivo="image/jpeg", tamanho_bytes=900,
        )
    )
    uc = ServicoAgendamentoUseCase(
        c_repo, m_repo, p_repo, _FakeStorageSimples(), cripto,
        _FabricaSeq(_EstrategiaErroSeq(erros)), LockMemoria(),
        max_tentativas_publicacao=3, backoff_base_segundos=60, relogio=lambda: relogio_fixo,
    )
    return uc, conta, midia, p_repo


async def test_rascunho_so_texto_bloqueia_agendamento_ate_anexar_midia() -> None:
    agora = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)
    uc, conta, midia, _ = await _preparar_uc([], agora)

    rascunho = await uc.criar_postagem(
        CriarPostagemCmd(
            empresa_id=conta.empresa_id, conta_ig_id=conta.id,
            tipo_midia=TipoMidia.IMAGE, legenda="Ideia de post sem foto ainda",
        )
    )
    assert rascunho.status == StatusPostagem.RASCUNHO and rascunho.midias_chaves == []

    with pytest.raises(ErroValidacaoDominio, match="exige exatamente 1 mídia"):
        await uc.agendar_postagem(
            AgendarPostagemCmd(conta.empresa_id, conta.id, rascunho.id, agora + timedelta(hours=1))
        )

    com_midia = await uc.anexar_midias(
        AnexarMidiasPostagemCmd(conta.empresa_id, conta.id, rascunho.id, midia_ids=(midia.id,))
    )
    assert com_midia.midias_chaves == [midia.chave_storage]
    agendada = await uc.agendar_postagem(
        AgendarPostagemCmd(conta.empresa_id, conta.id, rascunho.id, agora + timedelta(hours=1))
    )
    assert agendada.status == StatusPostagem.AGENDADO


async def test_retry_backoff_exponencial_e_falha_definitiva() -> None:
    agora = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)
    erros: list[Exception] = [
        ErroTransitorioMeta("Timeout rede"),
        ErroHttpMeta(503, "Meta indisponível"),
        ErroTransitorioMeta("Timeout final"),
    ]
    uc, conta, midia, _ = await _preparar_uc(erros, agora)
    post = await uc.criar_postagem(
        CriarPostagemCmd(
            conta.empresa_id, conta.id, TipoMidia.IMAGE,
            midia_ids=(midia.id,), agendado_para=agora,
        )
    )

    r1 = await uc.publicar_postagem(conta.empresa_id, conta.id, post.id)
    assert r1.reagendada is True and r1.postagem.tentativas_publicacao == 1
    assert r1.postagem.agendado_para == agora + timedelta(seconds=60)

    r2 = await uc.publicar_postagem(conta.empresa_id, conta.id, post.id)
    assert r2.reagendada is True and r2.postagem.tentativas_publicacao == 2
    assert r2.postagem.agendado_para == agora + timedelta(seconds=120)

    r3 = await uc.publicar_postagem(conta.empresa_id, conta.id, post.id)
    assert r3.reagendada is False and r3.postagem.status == StatusPostagem.FALHA

    uc_400, c2, m2, _ = await _preparar_uc([ErroHttpMeta(400, "URL inválida")], agora)
    p2 = await uc_400.criar_postagem(
        CriarPostagemCmd(
            c2.empresa_id, c2.id, TipoMidia.IMAGE, midia_ids=(m2.id,), agendado_para=agora
        )
    )
    r400 = await uc_400.publicar_postagem(c2.empresa_id, c2.id, p2.id)
    assert r400.reagendada is False and r400.postagem.status == StatusPostagem.FALHA
