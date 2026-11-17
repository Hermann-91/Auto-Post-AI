"""Testes unitários da exclusão de cards da Agenda e mídias da Biblioteca."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.aplicacao.biblioteca.servico_exclusao import ServicoExclusaoMidiaPostUseCase
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, StatusPostagem, TipoMidia
from app.infra.memoria.repo_conteudo_mem import InMemoryMidiaRepository
from app.infra.memoria.repo_publicacao_mem import InMemoryPostagemRepository


class _ContaRepoFake:
    def __init__(self, conta: ContaInstagram) -> None:
        self._conta = conta

    async def buscar_por_id(self, empresa_id: UUID, conta_ig_id: UUID) -> ContaInstagram | None:
        if self._conta.empresa_id == empresa_id and self._conta.id == conta_ig_id:
            return self._conta
        return None


class _StorageFake:
    def __init__(self) -> None:
        self.removidas: list[str] = []

    async def enviar_bytes(self, chave: str, conteudo: bytes, content_type: str) -> str:
        return chave

    async def baixar_bytes(self, chave: str) -> bytes:
        return b""

    async def obter_url_publica(self, chave: str) -> str:
        return chave

    async def remover_objeto(self, chave: str) -> None:
        self.removidas.append(chave)


async def test_excluir_postagem_apaga_exclusiva_e_preserva_favorita_compartilhada() -> None:
    emp_id = uuid4()
    conta = ContaInstagram(
        empresa_id=emp_id, ig_user_id="1", username="ig",
        access_token_enc="t", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    m_excl = MidiaBiblioteca(
        empresa_id=emp_id, conta_ig_id=conta.id, pasta=PastaMidia.IA_CRIA,
        chave_storage="excl.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=500,
    )
    m_fav = MidiaBiblioteca(
        empresa_id=emp_id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
        chave_storage="fav.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=600,
        curtida_favorita=True,
    )
    m_comp = MidiaBiblioteca(
        empresa_id=emp_id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
        chave_storage="comp.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=700,
    )
    midia_repo = InMemoryMidiaRepository()
    for m in (m_excl, m_fav, m_comp):
        await midia_repo.salvar(m)

    post_alvo = Postagem(
        empresa_id=emp_id, conta_ig_id=conta.id, tipo_midia=TipoMidia.CAROUSEL,
        midias_chaves=["excl.jpg", "fav.jpg", "comp.jpg"], status=StatusPostagem.RASCUNHO,
    )
    post_outro = Postagem(
        empresa_id=emp_id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
        midias_chaves=["comp.jpg"], status=StatusPostagem.AGENDADO,
    )
    post_repo = InMemoryPostagemRepository()
    await post_repo.salvar(post_alvo)
    await post_repo.salvar(post_outro)

    storage = _StorageFake()
    uc = ServicoExclusaoMidiaPostUseCase(_ContaRepoFake(conta), midia_repo, post_repo, storage)  # type: ignore[arg-type]

    res = await uc.excluir_postagem_agenda(emp_id, conta.id, post_alvo.id)
    assert res.midias_removidas_qtd == 1 and res.chaves_removidas == ["excl.jpg"]
    assert res.midias_preservadas_qtd == 2
    assert storage.removidas == ["excl.jpg"]
    assert await post_repo.buscar_por_id(emp_id, conta.id, post_alvo.id) is None
    assert await midia_repo.buscar_por_id(emp_id, conta.id, m_excl.id) is None
    assert await midia_repo.buscar_por_id(emp_id, conta.id, m_fav.id) is not None
    assert await midia_repo.buscar_por_id(emp_id, conta.id, m_comp.id) is not None


async def test_excluir_midia_biblioteca_bloqueia_post_ativo_e_permite_livre() -> None:
    emp_id = uuid4()
    conta = ContaInstagram(
        empresa_id=emp_id, ig_user_id="2", username="ig2",
        access_token_enc="t", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    m_ativa = MidiaBiblioteca(
        empresa_id=emp_id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
        chave_storage="ativa.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=400,
    )
    m_livre = MidiaBiblioteca(
        empresa_id=emp_id, conta_ig_id=conta.id, pasta=PastaMidia.IA_CRIA,
        chave_storage="livre.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=800,
    )
    midia_repo = InMemoryMidiaRepository()
    await midia_repo.salvar(m_ativa)
    await midia_repo.salvar(m_livre)

    post_repo = InMemoryPostagemRepository()
    await post_repo.salvar(
        Postagem(
            empresa_id=emp_id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
            midias_chaves=["ativa.jpg"], status=StatusPostagem.RASCUNHO,
        )
    )
    storage = _StorageFake()
    uc = ServicoExclusaoMidiaPostUseCase(_ContaRepoFake(conta), midia_repo, post_repo, storage)  # type: ignore[arg-type]

    with pytest.raises(ErroValidacaoDominio, match="Agenda"):
        await uc.excluir_midia_biblioteca(emp_id, conta.id, m_ativa.id)

    res = await uc.excluir_midia_biblioteca(emp_id, conta.id, m_livre.id)
    assert res.bytes_liberados == 800 and storage.removidas == ["livre.jpg"]
    assert await midia_repo.buscar_por_id(emp_id, conta.id, m_livre.id) is None
