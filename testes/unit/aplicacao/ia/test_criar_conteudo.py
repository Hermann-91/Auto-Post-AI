"""Testes unitários da criação de conteúdo híbrida e curadoria visual."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.aplicacao.ia.criar_conteudo import CriarConteudoUseCase
from app.aplicacao.ia.dtos import CriarConteudoCmd
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.servico_curadoria import ServicoCuradoriaVisualUseCase
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.excecoes import ErroCotaExcedida, ErroValidacaoDominio
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, StatusPostagem, TipoMidia
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryConfigIARepository,
    InMemoryContaIGRepository,
    InMemoryMidiaRepository,
    InMemoryRagRepository,
)
from app.infra.memoria.repo_publicacao_mem import (
    InMemoryCustoRepository,
    InMemoryPostagemRepository,
)
from app.infra.memoria.repo_tenant_mem import InMemoryEmpresaRepository
from app.infra.midia.estrategias_midia import FabricaEstrategiasMidia
from app.infra.midia.processador_imagem import ProcessadorImagem
from app.infra.storage.local_storage_adapter import LocalStorageAdapter


def _gerar_imagem_bytes(largura: int = 800, altura: int = 800, fmt: str = "PNG") -> bytes:
    buf = BytesIO()
    Image.new("RGB", (largura, altura), (40, 90, 140)).save(buf, format=fmt)
    return buf.getvalue()


class _FakeIA:
    def __init__(self) -> None:
        self.chamadas_imagem = 0
        self.ultima_imagem_base: str | None = None

    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, formato_json)
        return (
            json.dumps(
                {
                    "legenda": "Café passado na hora",
                    "hashtags": ["#cafe", "#artesanal"],
                    "prompt_visual": "Xícara fumegante ao amanhecer",
                    "roteiro_slides": ["Slide 1", "Slide 2"],
                }
            ),
            {"openrouter_gen_id": "g-txt", "modelo": modelo, "tokens_in": 80,
             "tokens_out": 40, "custo_usd": Decimal("0.0020")},
        )

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        _ = prompt
        self.chamadas_imagem += 1
        self.ultima_imagem_base = imagem_base_url
        return (
            _gerar_imagem_bytes(900, 900, "PNG"),
            {"openrouter_gen_id": "g-img", "modelo": modelo, "tokens_in": 40,
             "tokens_out": 1000, "custo_usd": Decimal("0.0400")},
        )

    async def analisar_imagem(
        self, system_prompt: str, user_prompt: str, imagem_data_url: str, modelo: str
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, imagem_data_url)
        return (
            "Foto nítida com iluminação natural quente.",
            {"openrouter_gen_id": "g-vis", "modelo": modelo, "tokens_in": 150,
             "tokens_out": 20, "custo_usd": Decimal("0.0005")},
        )


async def _montar_cenario(tmp_path: Path, max_itens: int = 250) -> dict[str, Any]:
    emp_repo = InMemoryEmpresaRepository()
    conta_repo = InMemoryContaIGRepository()
    cfg_repo = InMemoryConfigIARepository()
    rag_repo = InMemoryRagRepository()
    midia_repo = InMemoryMidiaRepository()
    post_repo = InMemoryPostagemRepository()
    custo_repo = InMemoryCustoRepository()
    storage = LocalStorageAdapter(tmp_path)

    emp = await emp_repo.salvar(Empresa(nome="Cafe SA", limite_mensal_usd=Decimal("10.00")))
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp.id, ig_user_id="10", username="cafe_sa",
            access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    ia = _FakeIA()
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    prompts = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)
    cota = CotaMidia(max_itens=max_itens, max_bytes=10_000_000)
    visual = GeradorVisualHibrido(
        midia_repo, storage, ia, orc, FabricaEstrategiasMidia(),
        ProcessadorImagem.compactar_entrada, cota,
    )
    criador = CriarConteudoUseCase(
        cfg_repo, midia_repo, post_repo, ia, orc, prompts, visual, cota
    )
    curadoria = ServicoCuradoriaVisualUseCase(
        midia_repo, storage, ia, orc, prompts, ProcessadorImagem.compactar_entrada
    )
    return {
        "emp": emp, "conta": conta, "ia": ia, "storage": storage,
        "midia_repo": midia_repo, "criador": criador, "curadoria": curadoria,
    }


async def test_criar_conteudo_com_nano_banana_pipeline_jpeg_e_edicao(tmp_path: Path) -> None:
    ctx = await _montar_cenario(tmp_path)
    emp, conta = ctx["emp"], ctx["conta"]

    res = await ctx["criador"].executar(
        CriarConteudoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
            tema="Lançamento café", gerar_imagem_ia=True,
        )
    )
    assert res.custo_total_usd == Decimal("0.0420")
    assert len(res.midias_geradas) == 1
    midia = res.midias_geradas[0]
    assert midia.pasta == PastaMidia.IA_CRIA
    assert res.postagem is not None and res.postagem.status == StatusPostagem.RASCUNHO
    jpeg = await ctx["storage"].baixar_bytes(midia.chave_storage)
    with Image.open(BytesIO(jpeg)) as img:
        assert img.format == "JPEG" and img.size == (1080, 1350)

    # Curadoria redimensiona miniatura e salva resumo_visual
    curada = await ctx["curadoria"].curar_midia(emp.id, conta.id, midia.id)
    assert "iluminação natural" in curada.resumo_visual

    # Edição envia base64 e grava em IA-Edita
    editado = await ctx["criador"].executar(
        CriarConteudoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, tipo_midia=TipoMidia.STORIES,
            tema="Stories café", editar_midia_id=midia.id,
        )
    )
    assert editado.legenda == ""
    assert editado.midias_geradas[0].pasta == PastaMidia.IA_EDITA
    assert ctx["ia"].ultima_imagem_base is not None
    assert ctx["ia"].ultima_imagem_base.startswith("data:image/jpeg;base64,")


async def test_validacoes_cota_pre_chamada_e_reels(tmp_path: Path) -> None:
    ctx = await _montar_cenario(tmp_path, max_itens=1)
    emp, conta = ctx["emp"], ctx["conta"]

    with pytest.raises(ErroValidacaoDominio):
        await ctx["criador"].executar(
            CriarConteudoCmd(
                empresa_id=emp.id, conta_ig_id=conta.id,
                tipo_midia=TipoMidia.REELS, tema="Vídeo", gerar_imagem_ia=True,
            )
        )

    await ctx["midia_repo"].salvar(
        MidiaBiblioteca(
            empresa_id=emp.id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
            chave_storage=f"{emp.id}/{conta.id}/originais/1.jpg",
            tipo_arquivo="image/jpeg", tamanho_bytes=100,
        )
    )
    with pytest.raises(ErroCotaExcedida):
        await ctx["criador"].executar(
            CriarConteudoCmd(
                empresa_id=emp.id, conta_ig_id=conta.id,
                tipo_midia=TipoMidia.IMAGE, tema="Novo", gerar_imagem_ia=True,
            )
        )
    assert ctx["ia"].chamadas_imagem == 0
