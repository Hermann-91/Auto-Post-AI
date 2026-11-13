"""Testes de integração do adaptador de storage local para dev/test."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.storage.local_storage_adapter import LocalStorageAdapter


async def test_local_storage_envia_le_e_remove_com_isolamento(tmp_path: Path) -> None:
    adapter = LocalStorageAdapter(base_dir=tmp_path, base_url="https://api.local/media")
    chave = "emp1/ig1/originais/foto.jpg"

    url = await adapter.enviar_bytes(chave, b"conteudo", "image/jpeg")
    assert url == f"https://api.local/media/{chave}"
    assert (tmp_path / chave).read_bytes() == b"conteudo"

    await adapter.remover_objeto(chave)
    assert not (tmp_path / chave).exists()


async def test_local_storage_bloqueia_path_traversal(tmp_path: Path) -> None:
    adapter = LocalStorageAdapter(base_dir=tmp_path)
    with pytest.raises(ErroValidacaoDominio):
        await adapter.enviar_bytes("../../etc/passwd", b"x", "text/plain")
