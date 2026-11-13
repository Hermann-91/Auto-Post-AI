"""Testes unitários do adaptador Argon2idHasher."""

from __future__ import annotations

from app.core.seguranca.senha_argon2 import Argon2idHasher


async def test_hash_e_verificacao_argon2id(hasher_rapido: Argon2idHasher) -> None:
    hash_gerado = await hasher_rapido.gerar_hash("SenhaForte#2026")

    assert hash_gerado.startswith("$argon2id$")
    assert await hasher_rapido.verificar("SenhaForte#2026", hash_gerado) is True
    assert await hasher_rapido.verificar("SenhaErrada", hash_gerado) is False


async def test_verificar_hash_invalido_e_dummy(hasher_rapido: Argon2idHasher) -> None:
    assert await hasher_rapido.verificar("qualquer", "hash-corrompido") is False
    await hasher_rapido.verificar_dummy("qualquer")
