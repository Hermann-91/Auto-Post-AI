"""Testes unitários da entidade MidiaBiblioteca."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import PastaMidia


def test_montar_chave_storage_e_protecao_limpeza() -> None:
    eid, cid = uuid4(), uuid4()
    chave = MidiaBiblioteca.montar_chave_storage(eid, cid, PastaMidia.IA_CRIA, "arte_01.jpg")
    assert chave == f"{eid}/{cid}/IA-Cria/arte_01.jpg"

    midia = MidiaBiblioteca(
        empresa_id=eid,
        conta_ig_id=cid,
        pasta=PastaMidia.IA_CRIA,
        chave_storage=chave,
        tipo_arquivo="image/jpeg",
        tamanho_bytes=120_000,
    )
    assert midia.pode_ser_limpa(vinculada_a_post_ativo=False) is True
    assert midia.pode_ser_limpa(vinculada_a_post_ativo=True) is False

    midia.alternar_curtida(True)
    assert midia.pode_ser_limpa(vinculada_a_post_ativo=False) is False


def test_rejeitar_path_traversal_no_nome_arquivo() -> None:
    with pytest.raises(ErroValidacaoDominio):
        MidiaBiblioteca.montar_chave_storage(
            uuid4(),
            uuid4(),
            PastaMidia.ORIGINAIS,
            "../segredo.jpg",
        )
