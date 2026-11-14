"""Testes unitários do upload na biblioteca, validação de cota e curtidas."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.aplicacao.biblioteca.dtos import UploadMidiaCmd
from app.aplicacao.biblioteca.servico_upload_cota import ServicoUploadCotaUseCase
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.excecoes import ErroCotaExcedida, ErroValidacaoDominio
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.dominio.objetos_valor.enums_conteudo import PastaMidia


class _FakeMidiaRepo:
    def __init__(self, falhar_ao_salvar: bool = False) -> None:
        self.itens: dict[UUID, MidiaBiblioteca] = {}
        self.falhar_ao_salvar = falhar_ao_salvar

    async def salvar(self, midia: MidiaBiblioteca) -> MidiaBiblioteca:
        if self.falhar_ao_salvar:
            raise RuntimeError("Erro simulado no banco")
        self.itens[midia.id] = midia
        return midia

    async def buscar_por_id(
        self, empresa_id: UUID, conta_ig_id: UUID, midia_id: UUID
    ) -> MidiaBiblioteca | None:
        item = self.itens.get(midia_id)
        if item and item.empresa_id == empresa_id and item.conta_ig_id == conta_ig_id:
            return item
        return None

    async def listar_por_conta(
        self, empresa_id: UUID, conta_ig_id: UUID, pasta: PastaMidia | None = None
    ) -> list[MidiaBiblioteca]:
        return [
            m
            for m in self.itens.values()
            if m.empresa_id == empresa_id
            and m.conta_ig_id == conta_ig_id
            and (pasta is None or m.pasta == pasta)
        ]

    async def calcular_uso_cota(self, empresa_id: UUID, conta_ig_id: UUID) -> tuple[int, int]:
        da_conta = await self.listar_por_conta(empresa_id, conta_ig_id)
        return len(da_conta), sum(m.tamanho_bytes for m in da_conta)

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, midia_id: UUID) -> None:
        self.itens.pop(midia_id, None)


class _FakeStorage:
    def __init__(self) -> None:
        self.objetos: dict[str, bytes] = {}
        self.removidas: list[str] = []

    async def enviar_bytes(self, chave: str, conteudo: bytes, content_type: str) -> str:
        _ = content_type
        self.objetos[chave] = conteudo
        return f"https://cdn.exemplo.com/{chave}"

    async def baixar_bytes(self, chave: str) -> bytes:
        return self.objetos.get(chave, b"")

    async def obter_url_publica(self, chave: str) -> str:
        return f"https://cdn.exemplo.com/{chave}"

    async def remover_objeto(self, chave: str) -> None:
        self.objetos.pop(chave, None)
        self.removidas.append(chave)


async def test_upload_valido_curtida_e_resumo_cota() -> None:
    repo = _FakeMidiaRepo()
    storage = _FakeStorage()
    uc = ServicoUploadCotaUseCase(repo, storage, CotaMidia(max_itens=5, max_bytes=10000))
    emp_id, conta_id = uuid4(), uuid4()

    res = await uc.registrar_upload(
        UploadMidiaCmd(
            empresa_id=emp_id,
            conta_ig_id=conta_id,
            pasta=PastaMidia.ORIGINAIS,
            nome_arquivo="foto perfil #1.png",
            content_type="image/png",
            conteudo=b"abc123",
        )
    )
    assert res.url_publica.startswith(f"https://cdn.exemplo.com/{emp_id}/{conta_id}/originais/")
    assert res.midia.chave_storage.endswith("_foto_perfil_1.png")
    assert res.midia.chave_storage in storage.objetos

    with pytest.raises(ErroValidacaoDominio):
        await uc.registrar_upload(
            UploadMidiaCmd(
                empresa_id=emp_id,
                conta_ig_id=conta_id,
                pasta=PastaMidia.ORIGINAIS,
                nome_arquivo="../segredo.png",
                content_type="image/png",
                conteudo=b"abc",
            )
        )

    curtida = await uc.alternar_curtida(emp_id, conta_id, res.midia.id, True)
    assert curtida.curtida_favorita is True

    cota = await uc.obter_resumo_cota(emp_id, conta_id)
    assert cota.itens_usados == 1 and cota.bytes_usados == 6


async def test_bloqueia_mime_invalido_e_excesso_cota() -> None:
    repo = _FakeMidiaRepo()
    storage = _FakeStorage()
    uc = ServicoUploadCotaUseCase(repo, storage, CotaMidia(max_itens=1, max_bytes=100))
    emp_id, conta_id = uuid4(), uuid4()

    with pytest.raises(ErroValidacaoDominio):
        await uc.registrar_upload(
            UploadMidiaCmd(
                empresa_id=emp_id,
                conta_ig_id=conta_id,
                pasta=PastaMidia.ORIGINAIS,
                nome_arquivo="doc.pdf",
                content_type="application/pdf",
                conteudo=b"123",
            )
        )

    await uc.registrar_upload(
        UploadMidiaCmd(
            empresa_id=emp_id,
            conta_ig_id=conta_id,
            pasta=PastaMidia.ORIGINAIS,
            nome_arquivo="ok.jpg",
            content_type="image/jpeg",
            conteudo=b"12345",
        )
    )
    with pytest.raises(ErroCotaExcedida):
        await uc.registrar_upload(
            UploadMidiaCmd(
                empresa_id=emp_id,
                conta_ig_id=conta_id,
                pasta=PastaMidia.ORIGINAIS,
                nome_arquivo="segunda.jpg",
                content_type="image/jpeg",
                conteudo=b"123",
            )
        )


async def test_compensa_removendo_do_storage_se_db_falhar() -> None:
    repo = _FakeMidiaRepo(falhar_ao_salvar=True)
    storage = _FakeStorage()
    uc = ServicoUploadCotaUseCase(repo, storage)

    with pytest.raises(RuntimeError):
        await uc.registrar_upload(
            UploadMidiaCmd(
                empresa_id=uuid4(),
                conta_ig_id=uuid4(),
                pasta=PastaMidia.IA_CRIA,
                nome_arquivo="arte.jpg",
                content_type="image/jpeg",
                conteudo=b"img",
            )
        )
    assert len(storage.objetos) == 0 and len(storage.removidas) == 1
