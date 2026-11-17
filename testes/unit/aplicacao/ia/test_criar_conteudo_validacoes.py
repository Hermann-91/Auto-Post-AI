"""Testes unitários de validação prévia de mídias e retry contra legenda vazia."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.aplicacao.ia.criar_conteudo import CriarConteudoUseCase
from app.aplicacao.ia.dtos import CriarConteudoCmd
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.excecoes import ErroIntegracaoIA, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, TipoMidia
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


class _FakeIARespostas:
    def __init__(self, respostas: list[dict[str, Any]]) -> None:
        self._respostas = respostas
        self.chamadas = 0

    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, formato_json)
        idx = min(self.chamadas, len(self._respostas) - 1)
        self.chamadas += 1
        return json.dumps(self._respostas[idx]), {
            "openrouter_gen_id": f"g-{self.chamadas}",
            "modelo": modelo,
            "tokens_in": 50,
            "tokens_out": 20,
            "custo_usd": Decimal("0.0010"),
        }

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        _ = (prompt, modelo, imagem_base_url)
        return b"", {}


async def _montar_criador(tmp_path: Path, ia: _FakeIARespostas) -> dict[str, Any]:
    emp_repo, conta_repo = InMemoryEmpresaRepository(), InMemoryContaIGRepository()
    cfg_repo, rag_repo = InMemoryConfigIARepository(), InMemoryRagRepository()
    midia_repo, post_repo = InMemoryMidiaRepository(), InMemoryPostagemRepository()
    custo_repo = InMemoryCustoRepository()
    emp = await emp_repo.salvar(Empresa(nome="Teste Validacao"))
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp.id, ig_user_id="99", username="teste_val",
            access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    prompts = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)
    visual = GeradorVisualHibrido(
        midia_repo, LocalStorageAdapter(tmp_path), ia, orc,
        FabricaEstrategiasMidia(), ProcessadorImagem.compactar_entrada,
    )
    criador = CriarConteudoUseCase(cfg_repo, midia_repo, post_repo, ia, orc, prompts, visual)
    return {"emp": emp, "conta": conta, "midia_repo": midia_repo,
            "post_repo": post_repo, "criador": criador}


async def test_bloqueia_multiplas_midias_em_image_antes_de_chamar_ia(tmp_path: Path) -> None:
    ia = _FakeIARespostas([{"legenda": "Ok", "hashtags": []}])
    ctx = await _montar_criador(tmp_path, ia)
    emp, conta = ctx["emp"], ctx["conta"]
    m1 = await ctx["midia_repo"].salvar(MidiaBiblioteca(
        empresa_id=emp.id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
        chave_storage="a.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=100,
    ))
    m2 = await ctx["midia_repo"].salvar(MidiaBiblioteca(
        empresa_id=emp.id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
        chave_storage="b.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=100,
    ))
    with pytest.raises(ErroValidacaoDominio, match="aceita no máximo 1 mídia"):
        await ctx["criador"].executar(CriarConteudoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
            tema="Autoridade", midia_base_ids=(m1.id, m2.id),
        ))
    assert ia.chamadas == 0


async def test_retry_automatico_quando_ia_retorna_legenda_vazia(tmp_path: Path) -> None:
    ia = _FakeIARespostas([
        {"legenda": "", "hashtags": [], "roteiro_slides": []},
        {"legenda": "Legenda completa recuperada no retry!", "hashtags": ["#3d"]},
    ])
    ctx = await _montar_criador(tmp_path, ia)
    res = await ctx["criador"].executar(CriarConteudoCmd(
        empresa_id=ctx["emp"].id, conta_ig_id=ctx["conta"].id,
        tipo_midia=TipoMidia.CAROUSEL, tema="Autoridade",
    ))
    assert ia.chamadas == 2
    assert res.legenda == "Legenda completa recuperada no retry!"
    assert res.postagem is not None and "#3d" in res.postagem.legenda


async def test_falha_quando_ia_persiste_com_legenda_vazia(tmp_path: Path) -> None:
    ia = _FakeIARespostas([{"legenda": "", "hashtags": [], "roteiro_slides": []}])
    ctx = await _montar_criador(tmp_path, ia)
    with pytest.raises(ErroIntegracaoIA, match="legenda vazia"):
        await ctx["criador"].executar(CriarConteudoCmd(
            empresa_id=ctx["emp"].id, conta_ig_id=ctx["conta"].id,
            tipo_midia=TipoMidia.CAROUSEL, tema="Autoridade",
        ))
    assert ia.chamadas == 2
    assert await ctx["post_repo"].listar_por_conta(ctx["emp"].id, ctx["conta"].id) == []
