"""Testes unitários da limpeza pós-postagem com proteção de favoritas e ativas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from app.aplicacao.biblioteca.servico_limpeza import ServicoLimpezaPosPostagemUseCase
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import Postagem
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, StatusPostagem, TipoMidia


class _MemMidiaRepo:
    def __init__(self, itens: list[MidiaBiblioteca]) -> None:
        self.itens = {m.id: m for m in itens}

    async def salvar(self, midia: MidiaBiblioteca) -> MidiaBiblioteca:
        self.itens[midia.id] = midia
        return midia

    async def buscar_por_id(
        self, empresa_id: UUID, conta_ig_id: UUID, midia_id: UUID
    ) -> MidiaBiblioteca | None:
        return self.itens.get(midia_id)

    async def listar_por_conta(
        self, empresa_id: UUID, conta_ig_id: UUID, pasta: PastaMidia | None = None
    ) -> list[MidiaBiblioteca]:
        return [
            m
            for m in self.itens.values()
            if m.empresa_id == empresa_id and m.conta_ig_id == conta_ig_id
        ]

    async def calcular_uso_cota(self, empresa_id: UUID, conta_ig_id: UUID) -> tuple[int, int]:
        return len(self.itens), sum(m.tamanho_bytes for m in self.itens.values())

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, midia_id: UUID) -> None:
        self.itens.pop(midia_id, None)


class _MemPostRepo:
    def __init__(self, posts: list[Postagem]) -> None:
        self.posts = posts

    async def salvar(self, postagem: Postagem) -> Postagem:
        return postagem

    async def buscar_por_id(
        self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID
    ) -> Postagem | None:
        return None

    async def listar_por_conta(
        self, empresa_id: UUID, conta_ig_id: UUID, status: StatusPostagem | None = None
    ) -> list[Postagem]:
        return [
            p
            for p in self.posts
            if p.empresa_id == empresa_id and p.conta_ig_id == conta_ig_id
        ]

    async def listar_agendadas_pendentes(self, ate_momento: datetime) -> list[Postagem]:
        return []

    async def listar_publicando_travadas(self, atualizado_ate: datetime) -> list[Postagem]:
        _ = atualizado_ate
        return []

    async def remover(
        self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID
    ) -> bool:
        _ = (empresa_id, conta_ig_id, postagem_id)
        return False


class _FakeStorageLimpeza:
    def __init__(self, falhar_chave: str | None = None) -> None:
        self.removidas: list[str] = []
        self.falhar_chave = falhar_chave

    async def enviar_bytes(self, chave: str, conteudo: bytes, content_type: str) -> str:
        return chave

    async def baixar_bytes(self, chave: str) -> bytes:
        return b""

    async def obter_url_publica(self, chave: str) -> str:
        return chave

    async def remover_objeto(self, chave: str) -> None:
        if chave == self.falhar_chave:
            raise OSError("Erro transitório S3")
        self.removidas.append(chave)


async def test_limpeza_remove_publicadas_e_protege_favoritas_agendadas_e_nao_postadas() -> None:
    emp_id, conta_id = uuid4(), uuid4()
    m_pub = MidiaBiblioteca(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        pasta=PastaMidia.PROCESSADAS,
        chave_storage="pub.jpg",
        tipo_arquivo="image/jpeg",
        tamanho_bytes=1000,
    )
    m_fav = MidiaBiblioteca(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        pasta=PastaMidia.IA_CRIA,
        chave_storage="fav.jpg",
        tipo_arquivo="image/jpeg",
        tamanho_bytes=2000,
        curtida_favorita=True,
    )
    m_agendada = MidiaBiblioteca(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        pasta=PastaMidia.ORIGINAIS,
        chave_storage="agendada.jpg",
        tipo_arquivo="image/jpeg",
        tamanho_bytes=3000,
    )
    m_virgem = MidiaBiblioteca(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        pasta=PastaMidia.ORIGINAIS,
        chave_storage="virgem.jpg",
        tipo_arquivo="image/jpeg",
        tamanho_bytes=4000,
    )
    post_pub = Postagem(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        tipo_midia=TipoMidia.CAROUSEL,
        midias_chaves=["pub.jpg", "fav.jpg", "agendada.jpg"],
        status=StatusPostagem.PUBLICADO,
    )
    post_agend = Postagem(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        tipo_midia=TipoMidia.IMAGE,
        midias_chaves=["agendada.jpg"],
        status=StatusPostagem.AGENDADO,
    )

    midia_repo = _MemMidiaRepo([m_pub, m_fav, m_agendada, m_virgem])
    storage = _FakeStorageLimpeza()
    uc = ServicoLimpezaPosPostagemUseCase(midia_repo, _MemPostRepo([post_pub, post_agend]), storage)

    res = await uc.executar(emp_id, conta_id)
    assert res.removidas_qtd == 1
    assert res.bytes_liberados == 1000
    assert res.chaves_removidas == ["pub.jpg"]
    assert res.falhas == 0
    assert m_pub.id not in midia_repo.itens
    assert {m_fav.id, m_agendada.id, m_virgem.id}.issubset(midia_repo.itens)


async def test_limpeza_mantem_registro_no_db_se_storage_falhar() -> None:
    emp_id, conta_id = uuid4(), uuid4()
    m_pub = MidiaBiblioteca(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        pasta=PastaMidia.PROCESSADAS,
        chave_storage="falha.jpg",
        tipo_arquivo="image/jpeg",
        tamanho_bytes=500,
    )
    post_pub = Postagem(
        empresa_id=emp_id,
        conta_ig_id=conta_id,
        tipo_midia=TipoMidia.IMAGE,
        midias_chaves=["falha.jpg"],
        status=StatusPostagem.PUBLICADO,
    )
    midia_repo = _MemMidiaRepo([m_pub])
    uc = ServicoLimpezaPosPostagemUseCase(
        midia_repo, _MemPostRepo([post_pub]), _FakeStorageLimpeza(falhar_chave="falha.jpg")
    )

    res = await uc.executar(emp_id, conta_id)
    assert res.removidas_qtd == 0 and res.falhas == 1
    assert m_pub.id in midia_repo.itens
