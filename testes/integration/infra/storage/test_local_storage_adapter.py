"""Testes de integração do adaptador de storage local para dev/test."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.storage.local_storage_adapter import LocalStorageAdapter


async def test_local_storage_envia_le_e_remove_com_isolamento(tmp_path: Path) -> None:
    adapter = LocalStorageAdapter(base_dir=tmp_path, base_url="https://api.local/media")
    chave = "emp1/ig1/originais/foto.jpg"

    url = await adapter.enviar_bytes(chave, b"conteudo", "image/jpeg")
    assert url == f"https://api.local/media/{chave}"
    assert (tmp_path / chave).read_bytes() == b"conteudo"
    assert await adapter.baixar_bytes(chave) == b"conteudo"

    await adapter.remover_objeto(chave)
    assert not (tmp_path / chave).exists()

    with pytest.raises(ErroValidacaoDominio):
        await adapter.baixar_bytes(chave)


async def test_local_storage_bloqueia_path_traversal(tmp_path: Path) -> None:
    adapter = LocalStorageAdapter(base_dir=tmp_path)
    chaves_maliciosas = (
        "../../etc/passwd",
        "..\\..\\etc\\passwd",
        "emp1/ig1/\x00foto.jpg",
        ".",
    )
    for chave_maliciosa in chaves_maliciosas:
        with pytest.raises(ErroValidacaoDominio):
            await adapter.enviar_bytes(chave_maliciosa, b"x", "text/plain")

    externo = tmp_path.parent / "segredo_host.txt"
    externo.write_bytes(b"segredo")
    link = tmp_path / "symlink_escape.jpg"
    link.symlink_to(externo)
    with pytest.raises(ErroValidacaoDominio):
        await adapter.baixar_bytes("symlink_escape.jpg")


async def test_local_storage_assina_e_valida_hmac(tmp_path: Path) -> None:
    adapter = LocalStorageAdapter(
        base_dir=tmp_path,
        base_url="https://vps.local/media",
        signing_secret="segredo-teste-hmac",
        presigned_ttl_segundos=120,
    )
    chave = "emp1/ig1/originais/foto.jpg"
    url = await adapter.enviar_bytes(chave, b"dados", "image/jpeg")
    qs = parse_qs(urlparse(url).query)
    exp = int(qs["exp"][0])
    sig = qs["sig"][0]

    caminho = adapter.validar_assinatura(chave, exp, sig)
    assert caminho.read_bytes() == b"dados"

    with pytest.raises(ErroValidacaoDominio):
        adapter.validar_assinatura(chave, exp, "assinatura_falsa")
    with pytest.raises(ErroValidacaoDominio):
        adapter.validar_assinatura(chave, 1, sig)
