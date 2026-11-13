"""Testes unitários extras: compactação na entrada, listagem, leitura e anti-IDOR."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from app.aplicacao.biblioteca.dtos import UploadMidiaCmd
from app.aplicacao.biblioteca.servico_upload_cota import ServicoUploadCotaUseCase
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.dominio.objetos_valor.enums_conteudo import PastaMidia
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryContaIGRepository,
    InMemoryMidiaRepository,
)
from app.infra.midia.processador_imagem import ProcessadorImagem
from app.infra.storage.local_storage_adapter import LocalStorageAdapter


def _png_grande() -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (2600, 1400), (40, 120, 200, 255)).save(buf, format="PNG")
    return buf.getvalue()


async def test_upload_compacta_imagem_lista_por_pasta_e_le_bytes(tmp_path: Path) -> None:
    emp_id = uuid4()
    conta_repo = InMemoryContaIGRepository()
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp_id,
            ig_user_id="12345",
            username="perfil_teste",
            access_token_enc="tok",
            token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    midia_repo = InMemoryMidiaRepository()
    storage = LocalStorageAdapter(tmp_path)
    uc = ServicoUploadCotaUseCase(
        midia_repo=midia_repo,
        storage=storage,
        cota=CotaMidia(max_itens=10, max_bytes=5_000_000),
        compactador=ProcessadorImagem.compactar_entrada,
        conta_repo=conta_repo,
    )

    res = await uc.registrar_upload(
        UploadMidiaCmd(
            empresa_id=emp_id,
            conta_ig_id=conta.id,
            pasta=PastaMidia.ORIGINAIS,
            nome_arquivo="arte.png",
            content_type="image/png",
            conteudo=_png_grande(),
        )
    )
    assert res.midia.tipo_arquivo == "image/jpeg"
    assert res.midia.chave_storage.endswith(".jpg")

    with Image.open(BytesIO(await storage.baixar_bytes(res.midia.chave_storage))) as img:
        assert max(img.size) <= 2048

    originais = await uc.listar_midias(emp_id, conta.id, pasta=PastaMidia.ORIGINAIS)
    ia_cria = await uc.listar_midias(emp_id, conta.id, pasta=PastaMidia.IA_CRIA)
    assert len(originais) == 1 and len(ia_cria) == 0

    meta, dados = await uc.obter_conteudo_midia(emp_id, conta.id, res.midia.id)
    assert meta.id == res.midia.id and dados.startswith(b"\xff\xd8")


async def test_bloqueia_acesso_a_conta_de_outra_empresa(tmp_path: Path) -> None:
    conta_repo = InMemoryContaIGRepository()
    emp_dona, emp_intrusa = uuid4(), uuid4()
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp_dona,
            ig_user_id="999",
            username="dona",
            access_token_enc="tok",
            token_expira_em=datetime.now(UTC) + timedelta(days=10),
        )
    )
    uc = ServicoUploadCotaUseCase(
        midia_repo=InMemoryMidiaRepository(),
        storage=LocalStorageAdapter(tmp_path),
        conta_repo=conta_repo,
    )
    with pytest.raises(ErroValidacaoDominio):
        await uc.listar_midias(emp_intrusa, conta.id)
    with pytest.raises(ErroValidacaoDominio):
        await uc.obter_resumo_cota(emp_intrusa, conta.id)
