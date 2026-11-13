"""Testes unitários de FernetCipher e rotação MultiFernet."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.seguranca.criptografia_fernet import FernetCipher
from app.dominio.excecoes import ErroSegurancaInterna


def test_criptografar_descriptografar_e_rotacao_chaves() -> None:
    chave_antiga = Fernet.generate_key().decode("utf-8")
    chave_nova = Fernet.generate_key().decode("utf-8")

    cipher_antigo = FernetCipher([chave_antiga])
    cifrado = cipher_antigo.criptografar("ig-long-lived-token-secreto")

    cipher_rotacionado = FernetCipher([chave_nova, chave_antiga])
    assert cipher_rotacionado.descriptografar(cifrado) == "ig-long-lived-token-secreto"


def test_falha_ao_descriptografar_token_adulterado() -> None:
    cipher = FernetCipher([Fernet.generate_key().decode("utf-8")])
    with pytest.raises(ErroSegurancaInterna):
        cipher.descriptografar("token-invalido")
