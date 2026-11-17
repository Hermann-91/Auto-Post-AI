"""Testes unitários de visão em fotos anexadas, rascunho só-texto e curadoria até 5 fotos."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

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
from app.dominio.excecoes import ErroValidacaoDominio
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


def _foto_bytes(cor: tuple[int, int, int] = (90, 50, 30)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1400, 1400), cor).save(buf, format="JPEG")
    return buf.getvalue()


class _FakeVisaoMultiIA:
    def __init__(self) -> None:
        self.ultimo_prompt_texto = ""
        self.analises_unicas: list[str] = []
        self.lotes_enviados: list[int] = []

    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, formato_json)
        self.ultimo_prompt_texto = user_prompt
        return json.dumps({
            "legenda": "Legenda guiada pela foto real", "hashtags": ["#cacau"],
            "roteiro_slides": [],
        }), {"modelo": modelo, "tokens_in": 60, "tokens_out": 30, "custo_usd": Decimal("0.0020")}

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        _ = (prompt, modelo, imagem_base_url)
        raise AssertionError("Não deve chamar geração de imagem paga")

    async def analisar_imagem(
        self, system_prompt: str, user_prompt: str, imagem_data_url: str, modelo: str
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt)
        self.analises_unicas.append(imagem_data_url)
        return json.dumps({
            "descricao_visual": "Barra de chocolate artesanal com nibs sobre madeira rústica.",
            "horario_sugerido": "19:30",
            "justificativa_horario": "Pico noturno de desejo gastronômico.",
        }), {"modelo": modelo, "tokens_in": 120, "tokens_out": 40, "custo_usd": Decimal("0.0010")}

    async def analisar_multiplas_imagens(
        self, system_prompt: str, user_prompt: str,
        imagens_data_urls: Sequence[str], modelo: str,
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt)
        self.lotes_enviados.append(len(imagens_data_urls))
        return json.dumps({
            "indice_vencedora": 2,
            "justificativa": "Foto 2 tem luz natural lateral superior e foco nítido.",
            "avaliacoes": [{"indice": 1, "nota": 7}, {"indice": 2, "nota": 9.5}],
        }), {"modelo": modelo, "tokens_in": 300, "tokens_out": 50, "custo_usd": Decimal("0.0015")}


async def _cenario_visao(tmp_path: Path) -> dict[str, Any]:
    emp_repo, conta_repo = InMemoryEmpresaRepository(), InMemoryContaIGRepository()
    cfg_repo, rag_repo = InMemoryConfigIARepository(), InMemoryRagRepository()
    midia_repo, post_repo = InMemoryMidiaRepository(), InMemoryPostagemRepository()
    custo_repo, storage = InMemoryCustoRepository(), LocalStorageAdapter(tmp_path)
    emp = await emp_repo.salvar(Empresa(nome="Cacau Brasil", limite_mensal_usd=Decimal("10")))
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp.id, ig_user_id="11", username="cacau_br",
            access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    ia = _FakeVisaoMultiIA()
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    prompts = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)
    visual = GeradorVisualHibrido(
        midia_repo, storage, ia, orc, FabricaEstrategiasMidia(),
        ProcessadorImagem.compactar_entrada,
    )
    criador = CriarConteudoUseCase(
        cfg_repo, midia_repo, post_repo, ia, orc, prompts, visual,
        cliente_visao=ia, storage=storage, compactador=ProcessadorImagem.compactar_entrada,
    )
    curadoria = ServicoCuradoriaVisualUseCase(
        midia_repo, storage, ia, orc, prompts, ProcessadorImagem.compactar_entrada
    )
    return {
        "emp": emp, "conta": conta, "ia": ia, "storage": storage,
        "midia_repo": midia_repo, "criador": criador, "curadoria": curadoria,
    }


async def test_visao_foto_anexada_rascunho_so_texto_e_curadoria_lote(tmp_path: Path) -> None:
    ctx = await _cenario_visao(tmp_path)
    emp, conta, ia = ctx["emp"], ctx["conta"], ctx["ia"]

    ids: list[Any] = []
    for idx in range(6):
        chave = f"{emp.id}/{conta.id}/originais/f{idx}.jpg"
        dados_f = _foto_bytes((30 + idx * 20, 80, 120))
        await ctx["storage"].enviar_bytes(chave, dados_f, "image/jpeg")
        m = await ctx["midia_repo"].salvar(
            MidiaBiblioteca(
                empresa_id=emp.id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
                chave_storage=chave, tipo_arquivo="image/jpeg", tamanho_bytes=2000,
            )
        )
        ids.append(m.id)

    res_foto = await ctx["criador"].executar(
        CriarConteudoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
            tema="Degustação", midia_base_ids=(ids[0],), gerar_imagem_ia=False,
        )
    )
    assert len(ia.analises_unicas) == 1
    assert "nibs sobre madeira rústica" in ia.ultimo_prompt_texto
    assert res_foto.horario_sugerido == "19:30"
    assert res_foto.custo_total_usd == Decimal("0.0030")

    res_texto = await ctx["criador"].executar(
        CriarConteudoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, tipo_midia=TipoMidia.CAROUSEL,
            tema="Benefícios do cacau", salvar_rascunho=True,
        )
    )
    assert res_texto.postagem is not None
    assert res_texto.postagem.status == StatusPostagem.RASCUNHO
    assert res_texto.postagem.midias_chaves == []

    eleita = await ctx["curadoria"].eleger_melhor_foto(
        emp.id, conta.id, ids[:5], objetivo_contexto="Maior conversão no feed"
    )
    assert ia.lotes_enviados == [5] and eleita.indice_vencedora == 2
    assert eleita.midia_vencedora.id == ids[1]

    with pytest.raises(ErroValidacaoDominio, match="1 e 5 fotos"):
        await ctx["curadoria"].eleger_melhor_foto(emp.id, conta.id, ids)
    with pytest.raises(ErroValidacaoDominio, match="pertence a esta conta"):
        await ctx["curadoria"].eleger_melhor_foto(emp.id, conta.id, [ids[0], uuid4()])
