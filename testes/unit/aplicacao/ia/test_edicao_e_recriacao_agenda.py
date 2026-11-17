"""Testes unitários para presets de melhoria e edição de orçamento semanal."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image

from app.aplicacao.ia.edicao_orcamento_semanal import EdicaoOrcamentoSemanalUseCase
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import PlanejamentoSemanal
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.objetos_valor.enums_conteudo import (
    PastaMidia,
    StatusPlanejamento,
)
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryConfigIARepository,
    InMemoryContaIGRepository,
    InMemoryMidiaRepository,
    InMemoryRagRepository,
)
from app.infra.memoria.repo_publicacao_mem import InMemoryPlanejamentoRepository
from app.infra.memoria.repo_tenant_mem import InMemoryEmpresaRepository
from app.infra.midia.processador_imagem import ProcessadorImagem


def _gerar_jpeg_bytes(cor: tuple[int, int, int] = (120, 80, 60)) -> bytes:
    img = Image.new("RGB", (600, 600), color=cor)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_processador_imagem_aplica_presets_melhoria() -> None:
    bruto = _gerar_jpeg_bytes()
    saida = ProcessadorImagem.otimizar_para_formato(
        bruto,
        proporcao="4:5",
        presets=["fullhd", "foto_profissional", "iluminacao"],
    )
    with Image.open(BytesIO(saida)) as img:
        assert img.size == (1080, 1350)
        assert img.mode == "RGB"


@pytest.mark.asyncio
async def test_encaixar_3_imagens_e_editar_resumo_orcamento_semanal() -> None:
    emp_repo = InMemoryEmpresaRepository()
    conta_repo = InMemoryContaIGRepository()
    cfg_repo = InMemoryConfigIARepository()
    midia_repo = InMemoryMidiaRepository()
    plano_repo = InMemoryPlanejamentoRepository()
    rag_repo = InMemoryRagRepository()

    empresa = await emp_repo.salvar(Empresa(nome="Gerai Artes"))
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=empresa.id,
            ig_user_id="1784",
            username="gerai_artes",
            access_token_enc="enc",
            token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    prompts_rag = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)
    uc = EdicaoOrcamentoSemanalUseCase(cfg_repo, midia_repo, plano_repo, prompts_rag)

    midias_ids = []
    for i in range(3):
        m = await midia_repo.salvar(
            MidiaBiblioteca(
                empresa_id=empresa.id,
                conta_ig_id=conta.id,
                pasta=PastaMidia.ORIGINAIS,
                chave_storage=f"{empresa.id}/{conta.id}/originais/foto_{i}.jpg",
                tipo_arquivo="image/jpeg",
                tamanho_bytes=1024,
                resumo_visual=f"Produto artesanal {i+1}",
            )
        )
        midias_ids.append(m.id)

    plano = PlanejamentoSemanal(
        empresa_id=empresa.id,
        conta_ig_id=conta.id,
        semana_inicio=date(2026, 11, 16),
        itens_grade=[
            {"ordem": 1, "dia_semana": "Seg", "formato": "IMAGE", "tema": "P1",
             "ideia_visual": "V1", "usar_ia_imagem": False},
            {"ordem": 2, "dia_semana": "Qua", "formato": "IMAGE", "tema": "P2",
             "ideia_visual": "V2", "usar_ia_imagem": False},
            {"ordem": 3, "dia_semana": "Sex", "formato": "REELS", "tema": "P3",
             "ideia_visual": "V3", "usar_ia_imagem": False},
        ],
        status=StatusPlanejamento.AGUARDANDO_APROVACAO,
    )
    await plano_repo.salvar(plano)

    plano_com_fotos = await uc.encaixar_midias_na_semana(
        empresa.id, conta.id, plano, tuple(midias_ids), ("fullhd", "iluminacao"), "Fundo de estúdio"
    )
    assert plano_com_fotos.itens_grade[0]["editar_midia_id"] == str(midias_ids[0])
    assert "fullhd" in plano_com_fotos.itens_grade[0]["presets_melhoria"]

    itens_editados = list(plano_com_fotos.itens_grade)
    itens_editados[0]["tema"] = "Tema Revisado pelo Usuário no Resumo"
    itens_editados[0]["formato"] = "STORIES"
    plano_revisado = await uc.atualizar_itens_orcamento(
        empresa.id, conta.id, plano.id, itens_editados
    )
    assert plano_revisado.itens_grade[0]["tema"] == "Tema Revisado pelo Usuário no Resumo"
    assert plano_revisado.itens_grade[0]["formato"] == "STORIES"
