"""Testes unitários do objeto de valor CotaMidia."""

from __future__ import annotations

import pytest

from app.dominio.excecoes import ErroCotaExcedida, ErroValidacaoDominio
from app.dominio.objetos_valor.cota_midia import CotaMidia


def test_cota_permite_dentro_dos_limites_e_calcula_percentuais() -> None:
    cota = CotaMidia(max_itens=10, max_bytes=1000)
    cota.validar_novo_arquivo(qtd_atual=9, bytes_atuais=800, novo_tamanho_bytes=200)

    assert cota.percentual_itens(5) == 50.0
    assert cota.percentual_bytes(250) == 25.0


def test_cota_bloqueia_excesso_de_itens_ou_bytes() -> None:
    cota = CotaMidia(max_itens=250, max_bytes=1000)
    with pytest.raises(ErroCotaExcedida):
        cota.validar_novo_arquivo(qtd_atual=250, bytes_atuais=100, novo_tamanho_bytes=50)
    with pytest.raises(ErroCotaExcedida):
        cota.validar_novo_arquivo(qtd_atual=10, bytes_atuais=950, novo_tamanho_bytes=51)


def test_cota_rejeita_parametros_nao_positivos() -> None:
    with pytest.raises(ErroValidacaoDominio):
        CotaMidia(max_itens=0, max_bytes=100)
