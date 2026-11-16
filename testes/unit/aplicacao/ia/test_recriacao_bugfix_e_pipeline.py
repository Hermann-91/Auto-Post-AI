"""Testes de separação Copywriter/Diretor e bugfix de recriação visual sem RAG bruto."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from app.aplicacao.ia.criar_conteudo import CriarConteudoUseCase
from app.aplicacao.ia.diretor_arte import DiretorArteService
from app.aplicacao.ia.dtos import CriarConteudoCmd
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.recriar_postagem_contexto import RecriarPostagemContextoUseCase
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.ia_rag import FonteRAG
from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG, TipoMidia
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


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (700, 700), (90, 120, 150)).save(buf, format="JPEG")
    return buf.getvalue()


class _FakePipelineCompleto:
    def __init__(self) -> None:
        self.chamadas_texto: list[tuple[str, str]] = []
        self.prompts_imagem: list[str] = []

    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = formato_json
        self.chamadas_texto.append((system_prompt, user_prompt))
        if "DIREÇÃO DE ARTE" in system_prompt:
            conteudo = json.dumps({
                "sujeito_principal": "Mesa com método V60",
                "acao_e_narrativa": "despejando café recém-passado",
                "ambiente": "cafeteria minimalista",
                "enquadramento_lente": "35mm lateral",
                "iluminacao": "luz da manhã",
                "paleta_e_clima": "quente e natural",
                "evitar": ["texto"],
                "prompt_imagem_final": "Mesa com método V60 e luz natural lateral",
            })
        else:
            conteudo = json.dumps({
                "legenda": "O segredo da extração equilibrada.",
                "hashtags": ["#cafe"], "roteiro_slides": [],
            })
        return conteudo, {"openrouter_gen_id": "t1", "modelo": modelo,
                          "tokens_in": 100, "tokens_out": 50, "custo_usd": Decimal("0.0020")}

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        _ = imagem_base_url
        self.prompts_imagem.append(prompt)
        return _jpeg_bytes(), {"openrouter_gen_id": "i1", "modelo": modelo,
                               "tokens_in": 50, "tokens_out": 800, "custo_usd": Decimal("0.0400")}

    async def analisar_imagem(
        self, system_prompt: str, user_prompt: str, imagem_data_url: str, modelo: str
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, imagem_data_url)
        return json.dumps({
            "anatomia_correta": True, "sem_texto_corrompido": True,
            "realismo_fotografico": True, "aderencia_ao_briefing": True,
            "aprovado": True, "diagnostico_correcao": "",
        }), {"openrouter_gen_id": "v1", "modelo": modelo,
             "tokens_in": 100, "tokens_out": 30, "custo_usd": Decimal("0.0010")}


async def test_separacao_copywriter_diretor_e_recriacao_sem_duplicacao_ou_rag(
    tmp_path: Path,
) -> None:
    emp_repo, conta_repo = InMemoryEmpresaRepository(), InMemoryContaIGRepository()
    cfg_repo, midia_repo = InMemoryConfigIARepository(), InMemoryMidiaRepository()
    post_repo, rag_repo = InMemoryPostagemRepository(), InMemoryRagRepository()
    custo_repo, storage = InMemoryCustoRepository(), LocalStorageAdapter(tmp_path)

    emp = await emp_repo.salvar(Empresa(nome="Cafe", limite_mensal_usd=Decimal("5.00")))
    conta = await conta_repo.salvar(ContaInstagram(
        empresa_id=emp.id, ig_user_id="1", username="cafe_real",
        access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    ))
    await rag_repo.salvar(FonteRAG(
        empresa_id=emp.id, conta_ig_id=conta.id, tipo=TipoFonteRAG.FAQ,
        titulo="Estacionamento Secreto",
        conteudo_limpo="Estacionamento gratuito na Rua das Flores numero 999.",
        chunks=["Estacionamento gratuito na Rua das Flores numero 999."],
    ))

    ia = _FakePipelineCompleto()
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    prompts = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)
    diretor = DiretorArteService(ia, orc)
    visual = GeradorVisualHibrido(
        midia_repo, storage, ia, orc, FabricaEstrategiasMidia(),
        ProcessadorImagem.compactar_entrada, cliente_visao=ia,
    )
    criador = CriarConteudoUseCase(
        cfg_repo, midia_repo, post_repo, ia, orc, prompts, visual, diretor_arte=diretor
    )

    res = await criador.executar(CriarConteudoCmd(
        empresa_id=emp.id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
        tema="Extração no V60", gerar_imagem_ia=True, pilar_editorial="Educação",
        modo_serie=True, etapa_serie="1/3", prompt_avancado="Mãos do barista em primeiro plano",
    ))
    assert len(ia.chamadas_texto) == 2
    assert "prompt_visual" not in ia.chamadas_texto[0][1]
    assert "DIREÇÃO DE ARTE" in ia.chamadas_texto[1][0]
    assert res.qualidade_revisao is not None and res.qualidade_revisao["status"] == "PASS"
    assert res.revisoes_visuais == 1 and res.tentativas_geracao_imagem == 1

    post = await post_repo.salvar(Postagem(
        empresa_id=emp.id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
        midias_chaves=[res.midias_geradas[0].chave_storage],
        legenda="Estacionamento e café especial",
    ))
    recriador = RecriarPostagemContextoUseCase(
        cfg_repo, midia_repo, post_repo, ia, orc, prompts, visual, diretor_arte=diretor
    )
    instrucao_unica = "Trocar ângulo para close na xícara fumegante"
    await recriador.recriar_com_contexto(
        emp.id, conta.id, post.id, "imagem", instrucao_unica
    )
    ultimo_prompt_img = ia.prompts_imagem[-1]
    assert ultimo_prompt_img.count(instrucao_unica) == 1
    assert "Rua das Flores" not in ultimo_prompt_img
    assert "Cultura:" not in ultimo_prompt_img
