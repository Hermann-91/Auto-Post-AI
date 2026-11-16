"""Testes unitários de RAG híbrido, Brand Bible, templates_json e multi-nicho."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.aplicacao.ia.dtos import AtualizarConfigIACmd, IndexarFonteRagCmd
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryConfigIARepository,
    InMemoryContaIGRepository,
    InMemoryRagRepository,
)
from app.infra.memoria.repo_publicacao_mem import InMemoryCustoRepository
from app.infra.memoria.repo_tenant_mem import InMemoryEmpresaRepository


class _FakeEmbeddings:
    async def gerar_embeddings(
        self, textos: list[str], modelo: str
    ) -> tuple[list[list[float]], dict[str, Any]]:
        vetores = []
        for t in textos:
            low = t.lower()
            if any(k in low for k in ("espresso", "torra", "cafe")):
                vetores.append([1.0, 0.0, 0.0])
            elif any(k in low for k in ("pilates", "coluna", "postura")):
                vetores.append([0.0, 1.0, 0.0])
            else:
                vetores.append([0.0, 0.0, 1.0])
        return vetores, {
            "openrouter_gen_id": "emb-fake",
            "modelo": modelo,
            "tokens_in": len(textos) * 10,
            "tokens_out": 0,
            "custo_usd": Decimal("0.000100"),
        }


async def test_rag_hibrido_descarta_irrelevante_e_isola_nichos_com_brand_bible() -> None:
    emp_repo = InMemoryEmpresaRepository()
    conta_repo = InMemoryContaIGRepository()
    cfg_repo = InMemoryConfigIARepository()
    rag_repo = InMemoryRagRepository()
    custo_repo = InMemoryCustoRepository()

    emp = await emp_repo.salvar(Empresa(nome="Agencia Multi", limite_mensal_usd=Decimal("5.00")))
    exp = datetime.now(UTC) + timedelta(days=30)
    conta_cafe = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp.id, ig_user_id="1", username="cafe_aurora",
            access_token_enc="tok", token_expira_em=exp,
        )
    )
    conta_pilates = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp.id, ig_user_id="2", username="studio_coluna",
            access_token_enc="tok", token_expira_em=exp,
        )
    )

    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    uc = ServicoPromptsRagUseCase(
        conta_repo, cfg_repo, rag_repo, cliente_embeddings=_FakeEmbeddings(), orcamento=orc
    )

    cfg_cafe = await uc.atualizar_config(
        AtualizarConfigIACmd(
            empresa_id=emp.id, conta_ig_id=conta_cafe.id,
            persona_json={"marca": "Café Aurora", "nicho": "cafeteria", "regiao": "Curitiba"},
            templates_json={"CAROUSEL": "Slide 1 gancho sensorial, ultimo slide convite."},
            aplicar_logo_padrao=False,
            modelo_texto_pref="deepseek/deepseek-v4-flash",
            modelo_img_pref="google/gemini-3.1-flash-image",
        )
    )
    await uc.atualizar_config(
        AtualizarConfigIACmd(
            empresa_id=emp.id, conta_ig_id=conta_pilates.id,
            persona_json={"marca": "Studio Coluna", "nicho": "pilates", "regiao": "Recife"},
            templates_json={"REELS": "Demonstracao de postura em 3 passos."},
            aplicar_logo_padrao=False,
            modelo_texto_pref="deepseek/deepseek-v4-flash",
            modelo_img_pref="google/gemini-3.1-flash-image",
        )
    )

    await uc.indexar_fonte(
        IndexarFonteRagCmd(
            empresa_id=emp.id, conta_ig_id=conta_cafe.id, tipo=TipoFonteRAG.DOCUMENTO,
            titulo="Manual Graos", conteudo="Torra media de cafe arabica para espresso doce.",
        )
    )
    await uc.indexar_fonte(
        IndexarFonteRagCmd(
            empresa_id=emp.id, conta_ig_id=conta_cafe.id, tipo=TipoFonteRAG.FAQ,
            titulo="Estacionamento", conteudo="Convenio na rua lateral ate 20h.",
        )
    )
    await uc.indexar_fonte(
        IndexarFonteRagCmd(
            empresa_id=emp.id, conta_ig_id=conta_pilates.id, tipo=TipoFonteRAG.URL,
            titulo="Guia Postura", conteudo="Mobilidade de coluna e respiracao no pilates.",
        )
    )

    trechos_cafe = await uc.recuperar_contexto(emp.id, conta_cafe.id, "extracao de cafe espresso")
    assert len(trechos_cafe) == 1
    assert "Manual Graos" in trechos_cafe[0]
    assert all("Estacionamento" not in t and "Guia Postura" not in t for t in trechos_cafe)

    trechos_sem = await uc.recuperar_contexto(emp.id, conta_cafe.id, "bebida cafe")
    assert trechos_sem and "Manual Graos" in trechos_sem[0]

    cfg_cafe_atual = await uc.obter_config(emp.id, conta_cafe.id)
    assert cfg_cafe_atual.brand_bible_json["nicho"] == "cafeteria"
    assert cfg_cafe_atual.brand_bible_json["fatos_chave_rag"]
    sys_prompt = uc.montar_system_prompt(conta_cafe, cfg_cafe_atual)
    assert "[NÚCLEO ESTRUTURAL GLOBAL]" in sys_prompt
    assert "[TEMPLATES ATIVOS DA CONTA]" in sys_prompt
    assert "Slide 1 gancho sensorial" in sys_prompt
    assert "Studio Coluna" not in sys_prompt and cfg_cafe.brand_bible_json["marca"] == "Café Aurora"
