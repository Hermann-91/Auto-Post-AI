"""Testes unitários para melhoria de imagem, edição de orçamento semanal e recriação na Agenda."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.aplicacao.ia.edicao_orcamento_semanal import EdicaoOrcamentoSemanalUseCase
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.recriar_postagem_contexto import RecriarPostagemContextoUseCase
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.ia_rag import FonteRAG
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import PlanejamentoSemanal, Postagem
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.objetos_valor.enums_conteudo import (
    PastaMidia,
    StatusPlanejamento,
    TipoFonteRAG,
    TipoMidia,
)
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryConfigIARepository,
    InMemoryContaIGRepository,
    InMemoryMidiaRepository,
    InMemoryRagRepository,
)
from app.infra.memoria.repo_publicacao_mem import (
    InMemoryCustoRepository,
    InMemoryPlanejamentoRepository,
    InMemoryPostagemRepository,
)
from app.infra.memoria.repo_tenant_mem import InMemoryEmpresaRepository
from app.infra.midia.estrategias_midia import FabricaEstrategiasMidia
from app.infra.midia.processador_imagem import ProcessadorImagem
from app.infra.storage.local_storage_adapter import LocalStorageAdapter


def _gerar_jpeg_bytes(cor: tuple[int, int, int] = (120, 80, 60)) -> bytes:
    img = Image.new("RGB", (600, 600), color=cor)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class _FakeClienteIA:
    """Fake determinístico de ClienteIAPort para testes unitários."""

    def __init__(self, img_bytes: bytes) -> None:
        self._img_bytes = img_bytes

    async def gerar_texto(
        self,
        system_prompt: str,
        user_prompt: str,
        modelo: str,
        formato_json: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, formato_json)
        resposta = json.dumps(
            {
                "legenda": "Nova legenda poética com café especial e cultura RAG",
                "hashtags": ["#cafeespecial", "#designautoral"],
            }
        )
        usage = {
            "modelo": modelo,
            "tokens_in": 120,
            "tokens_out": 60,
            "custo_usd": Decimal("0.0020"),
        }
        return resposta, usage

    async def analisar_imagem(
        self,
        system_prompt: str,
        user_prompt: str,
        imagem_data_url: str,
        modelo: str,
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, imagem_data_url)
        return "Descrição visual fake", {"modelo": modelo, "custo_usd": Decimal("0.0015")}

    async def gerar_ou_editar_imagem(
        self,
        prompt: str,
        modelo: str,
        imagem_base_url: str | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        _ = (prompt, imagem_base_url)
        usage = {
            "modelo": modelo,
            "tokens_in": 80,
            "tokens_out": 200,
            "custo_usd": Decimal("0.0200"),
        }
        return self._img_bytes, usage


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


@pytest.mark.asyncio
async def test_recriar_postagem_com_contexto_e_cultura_rag(tmp_path: Path) -> None:
    emp_repo = InMemoryEmpresaRepository()
    conta_repo = InMemoryContaIGRepository()
    cfg_repo = InMemoryConfigIARepository()
    midia_repo = InMemoryMidiaRepository()
    post_repo = InMemoryPostagemRepository()
    rag_repo = InMemoryRagRepository()
    custo_repo = InMemoryCustoRepository()
    storage = LocalStorageAdapter(tmp_path)

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
    await rag_repo.salvar(
        FonteRAG(
            empresa_id=empresa.id,
            conta_ig_id=conta.id,
            tipo=TipoFonteRAG.TEXTO,
            titulo="Cultura Marca",
            conteudo_limpo="Nossa cultura valoriza design autoral e café especial.",
            chunks=["Nossa cultura valoriza design autoral e café especial."],
        )
    )
    chave_inicial = f"{empresa.id}/{conta.id}/originais/inicial.jpg"
    await storage.enviar_bytes(chave_inicial, _gerar_jpeg_bytes(), "image/jpeg")
    post = await post_repo.salvar(
        Postagem(
            empresa_id=empresa.id,
            conta_ig_id=conta.id,
            tipo_midia=TipoMidia.IMAGE,
            midias_chaves=[chave_inicial],
            legenda="Legenda original simples",
        )
    )

    orcamento = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    prompts_rag = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)
    cliente_ia = _FakeClienteIA(_gerar_jpeg_bytes((40, 90, 140)))
    visual = GeradorVisualHibrido(
        midia_repo,
        storage,
        cliente_ia,
        orcamento,
        FabricaEstrategiasMidia(),
        ProcessadorImagem.compactar_entrada,
    )
    uc = RecriarPostagemContextoUseCase(
        cfg_repo, midia_repo, post_repo, cliente_ia, orcamento, prompts_rag, visual
    )

    post_txt = await uc.recriar_com_contexto(
        empresa.id, conta.id, post.id, "texto", "Deixar mais poético e citar café especial"
    )
    assert "café especial" in post_txt.legenda

    post_img = await uc.recriar_com_contexto(
        empresa.id, conta.id, post.id, "imagem", "Iluminação de estúdio profissional", ("fullhd",)
    )
    assert post_img.midias_chaves[0] != chave_inicial
