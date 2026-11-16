"""Testes unitários de Persona, chunking RAG e recuperação isolada por conta."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.aplicacao.ia.dtos import AtualizarConfigIACmd, IndexarFonteRagCmd
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase, segmentar_em_chunks
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, TipoFonteRAG
from app.infra.memoria.repo_conteudo_mem import (
    InMemoryConfigIARepository,
    InMemoryContaIGRepository,
    InMemoryRagRepository,
)


def test_segmentacao_preserva_palavras_com_sobreposicao() -> None:
    texto = " ".join(f"palavra{i}" for i in range(120))
    chunks = segmentar_em_chunks(texto, max_chars=200, overlap=30)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    assert chunks[0].split()[-1] in chunks[1]


async def test_rag_recupera_relevante_e_isola_contas() -> None:
    conta_repo = InMemoryContaIGRepository()
    cfg_repo = InMemoryConfigIARepository()
    rag_repo = InMemoryRagRepository()
    emp_id = uuid4()
    exp = datetime.now(UTC) + timedelta(days=30)

    conta_a = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp_id, ig_user_id="1", username="cafe_bom",
            access_token_enc="tok", token_expira_em=exp,
        )
    )
    conta_b = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp_id, ig_user_id="2", username="outra_conta",
            access_token_enc="tok", token_expira_em=exp,
        )
    )
    uc = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)

    cfg = await uc.atualizar_config(
        AtualizarConfigIACmd(
            empresa_id=emp_id, conta_ig_id=conta_a.id,
            persona_json={"marca": "Café Aurora", "nicho": "cafeteria", "tom_voz": "acolhedor"},
            templates_json={}, aplicar_logo_padrao=False,
            modelo_texto_pref="deepseek/deepseek-v4-flash",
            modelo_img_pref="google/gemini-3.1-flash-image",
        )
    )
    prompt_sys = uc.montar_system_prompt(conta_a, cfg)
    assert "Café Aurora" in prompt_sys and "Pé da Mata" not in prompt_sys

    await uc.indexar_fonte(
        IndexarFonteRagCmd(
            empresa_id=emp_id, conta_ig_id=conta_a.id, tipo=TipoFonteRAG.FAQ,
            titulo="Cardápio", conteudo="Temos espresso duplo, cappuccino e torta de limão.",
        )
    )
    await uc.indexar_fonte(
        IndexarFonteRagCmd(
            empresa_id=emp_id, conta_ig_id=conta_a.id, tipo=TipoFonteRAG.FAQ,
            titulo="Estacionamento", conteudo="Convênio com garagem na esquina.",
        )
    )
    await uc.indexar_fonte(
        IndexarFonteRagCmd(
            empresa_id=emp_id, conta_ig_id=conta_b.id, tipo=TipoFonteRAG.TEXTO,
            titulo="Segredo B", conteudo="Espresso secreto da conta B.",
        )
    )

    trechos = await uc.recuperar_contexto(emp_id, conta_a.id, "receita cappuccino espresso")
    assert trechos and "Cardápio" in trechos[0]
    assert all("Segredo B" not in t for t in trechos)

    with pytest.raises(ErroValidacaoDominio):
        await uc.exigir_conta(uuid4(), conta_a.id)


def test_formatar_ancoras_prioriza_curtida_favorita() -> None:
    emp_id, conta_id = uuid4(), uuid4()
    normal = MidiaBiblioteca(
        empresa_id=emp_id, conta_ig_id=conta_id, pasta=PastaMidia.ORIGINAIS,
        chave_storage="a/b/originais/n.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=100,
        curtida_favorita=False, resumo_visual="Mesa simples",
    )
    fav = MidiaBiblioteca(
        empresa_id=emp_id, conta_ig_id=conta_id, pasta=PastaMidia.IA_CRIA,
        chave_storage="a/b/IA-Cria/f.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=100,
        curtida_favorita=True, resumo_visual="Luz dourada de manhã",
    )
    texto = ServicoPromptsRagUseCase.formatar_ancoras_visuais([normal, fav], limite=2)
    assert "[ANTI-REPETIÇÃO" in texto
    assert "[DNA_FAVORITO_NAO_COPIAR] Luz dourada de manhã" in texto
    serie = ServicoPromptsRagUseCase.formatar_ancoras_visuais(
        [normal, fav], limite=2, modo_serie=True
    )
    assert "[CONTINUIDADE DE SÉRIE" in serie and "BASE_SERIE_FAVORITA" in serie
