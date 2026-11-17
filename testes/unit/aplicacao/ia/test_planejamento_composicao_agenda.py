"""Testes unitários de composição dinâmica, rascunho só-texto e auto-agendamento UTC."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from app.aplicacao.ia.criar_conteudo import CriarConteudoUseCase
from app.aplicacao.ia.dtos import ProporPlanejamentoCmd
from app.aplicacao.ia.edicao_orcamento_semanal import EdicaoOrcamentoSemanalUseCase
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.planejamento_semanal import PlanejamentoSemanalUseCase
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_plano_semanal
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, StatusPostagem
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


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (600, 600), (100, 120, 80)).save(buf, format="PNG")
    return buf.getvalue()


class _FakeIAComposicao:
    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, formato_json)
        if "Planeje" in user_prompt:
            conteudo = json.dumps({
                "itens": [
                    {"dia_semana": "Segunda", "horario_sugerido": "18:00", "formato": "IMAGE",
                     "tema": "Post 1", "usar_ia_imagem": True},
                    {"dia_semana": "Quarta", "horario_sugerido": "12:00", "formato": "IMAGE",
                     "tema": "Post 2", "usar_ia_imagem": True},
                    {"dia_semana": "Sexta", "horario_sugerido": "20:00", "formato": "REELS",
                     "tema": "Reels Bastidor", "usar_ia_imagem": True},
                ]
            })
        else:
            conteudo = json.dumps({
                "legenda": "Texto da semana", "hashtags": ["#marca"], "roteiro_slides": [],
            })
        return conteudo, {"modelo": modelo, "tokens_in": 50, "tokens_out": 40,
                          "custo_usd": Decimal("0.0020")}

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        _ = (prompt, imagem_base_url)
        return _png_bytes(), {"modelo": modelo, "tokens_in": 20, "tokens_out": 500,
                              "custo_usd": Decimal("0.0200")}


class _FakeTendenciasComp:
    async def buscar_tendencias(
        self, nicho: str, regiao: str, ttl_horas: int = 48
    ) -> dict[str, Any]:
        return {"nicho": nicho, "regiao": regiao, "ttl_horas": ttl_horas, "topicos": []}


async def test_composicao_dinamica_rascunho_so_texto_e_auto_agendar_utc(tmp_path: Path) -> None:
    emp_repo, conta_repo = InMemoryEmpresaRepository(), InMemoryContaIGRepository()
    cfg_repo, rag_repo = InMemoryConfigIARepository(), InMemoryRagRepository()
    midia_repo, plano_repo = InMemoryMidiaRepository(), InMemoryPlanejamentoRepository()
    post_repo, custo_repo = InMemoryPostagemRepository(), InMemoryCustoRepository()
    storage = LocalStorageAdapter(tmp_path)

    emp = await emp_repo.salvar(Empresa(nome="Agencia", limite_mensal_usd=Decimal("10")))
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp.id, ig_user_id="22", username="agencia",
            access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    ia = _FakeIAComposicao()
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    prompts = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)
    visual = GeradorVisualHibrido(
        midia_repo, storage, ia, orc, FabricaEstrategiasMidia(),
        ProcessadorImagem.compactar_entrada,
    )
    criador = CriarConteudoUseCase(cfg_repo, midia_repo, post_repo, ia, orc, prompts, visual)
    uc = PlanejamentoSemanalUseCase(
        cfg_repo, midia_repo, plano_repo, ia, _FakeTendenciasComp(), orc, prompts, criador
    )
    edicao = EdicaoOrcamentoSemanalUseCase(cfg_repo, midia_repo, plano_repo, prompts)

    # 1. Composição 2 IMAGE + 1 REELS com auto_agendar=True em America/Sao_Paulo
    proposta = await uc.propor_semana(
        ProporPlanejamentoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, semana_inicio=date(2027, 1, 4),
            composicao_formatos={"IMAGE": 2, "REELS": 1}, auto_agendar=True,
            fuso_horario="America/Sao_Paulo", incluir_imagens_ia=True,
        )
    )
    assert [it["formato"] for it in proposta.itens_grade] == ["IMAGE", "IMAGE", "REELS"]
    assert proposta.itens_grade[2]["usar_ia_imagem"] is False

    await uc.aprovar_plano(emp.id, conta.id, proposta.id)
    exec_res = await uc.executar_plano(emp.id, conta.id, proposta.id)
    assert len(exec_res.postagens_criadas) == 3
    p_seg, p_qua, p_sex = exec_res.postagens_criadas
    assert p_seg.status == StatusPostagem.AGENDADO
    assert p_seg.agendado_para == datetime(2027, 1, 4, 21, 0, tzinfo=UTC)
    assert p_qua.agendado_para == datetime(2027, 1, 6, 15, 0, tzinfo=UTC)
    assert p_sex.status == StatusPostagem.RASCUNHO and p_sex.midias_chaves == []

    # 2. Modo Só Texto cria rascunhos na Agenda (bugfix salvar_rascunho=True)
    plano_txt = await uc.propor_semana(
        ProporPlanejamentoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, semana_inicio=date(2027, 1, 11),
            quantidade_posts=2, incluir_imagens_ia=False,
        )
    )
    await uc.aprovar_plano(emp.id, conta.id, plano_txt.id)
    exec_txt = await uc.executar_plano(emp.id, conta.id, plano_txt.id)
    assert len(exec_txt.postagens_criadas) == 2
    assert all(p.status == StatusPostagem.RASCUNHO and not p.midias_chaves
               for p in exec_txt.postagens_criadas)

    # 3. Edição de orçamento: anexo de visão soma custo de visão e REELS não cobra imagem IA
    plano_edit = await uc.propor_semana(
        ProporPlanejamentoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, semana_inicio=date(2027, 1, 18),
            quantidade_posts=2, incluir_imagens_ia=False,
        )
    )
    midia = await midia_repo.salvar(
        MidiaBiblioteca(
            empresa_id=emp.id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
            chave_storage="x.jpg", tipo_arquivo="image/jpeg", tamanho_bytes=100,
        )
    )
    itens_edit = [
        {"formato": "IMAGE", "tema": "Anexo", "usar_ia_imagem": False,
         "midia_base_ids": [str(midia.id)]},
        {"formato": "REELS", "tema": "Reels", "usar_ia_imagem": True},
    ]
    atual = await edicao.atualizar_itens_orcamento(emp.id, conta.id, plano_edit.id, itens_edit)
    assert atual.itens_grade[1]["usar_ia_imagem"] is False
    esperado = estimar_plano_semanal(atual.itens_grade, "deepseek/deepseek-v4-flash",
                                     "google/gemini-3.1-flash-image")
    assert atual.custo_estimado_usd == esperado and esperado > Decimal("0.0040")

    # 4. Re-execução de plano concluído preserva REELS sem converter para IMAGE
    reexec = await uc.executar_plano(emp.id, conta.id, proposta.id)
    assert [p.tipo_midia.value for p in reexec.postagens_criadas] == ["IMAGE", "IMAGE", "REELS"]
    assert reexec.plano.itens_grade[2]["usar_ia_imagem"] is False
