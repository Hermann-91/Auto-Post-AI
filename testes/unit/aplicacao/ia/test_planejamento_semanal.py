"""Testes unitários do Planejamento Semanal Automatizado em 2 etapas."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.aplicacao.ia.criar_conteudo import CriarConteudoUseCase
from app.aplicacao.ia.dtos import ProporPlanejamentoCmd
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.planejamento_semanal import PlanejamentoSemanalUseCase
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.publicacao import PlanejamentoSemanal
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.excecoes import ErroOrcamentoExcedido, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import StatusPlanejamento
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
    Image.new("RGB", (600, 600), (150, 80, 40)).save(buf, format="PNG")
    return buf.getvalue()


class _FakeIAPlano:
    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, formato_json)
        if "Planeje" in user_prompt:
            conteudo = json.dumps(
                {
                    "itens": [
                        {
                            "dia_semana": "Segunda", "formato": "IMAGE", "tema": "Dica 1",
                            "objetivo": "salvar", "ideia_visual": "Mesa limpa",
                            "usar_ia_imagem": True,
                        },
                        {
                            "dia_semana": "Quarta", "formato": "STORIES", "tema": "Enquete",
                            "objetivo": "interagir", "ideia_visual": "Bastidor",
                            "usar_ia_imagem": True,
                        },
                    ]
                }
            )
        else:
            conteudo = json.dumps(
                {
                    "legenda": "Texto gerado", "hashtags": ["#dica"],
                    "prompt_visual": "Cena editorial", "roteiro_slides": [],
                }
            )
        return conteudo, {
            "openrouter_gen_id": "g-p", "modelo": modelo,
            "tokens_in": 90, "tokens_out": 60, "custo_usd": Decimal("0.0020"),
        }

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        _ = (prompt, imagem_base_url)
        return _png_bytes(), {
            "openrouter_gen_id": "g-i", "modelo": modelo,
            "tokens_in": 30, "tokens_out": 900, "custo_usd": Decimal("0.0400"),
        }


class _FakeTendencias:
    async def buscar_tendencias(
        self, nicho: str, regiao: str, ttl_horas: int = 48
    ) -> dict[str, Any]:
        return {
            "nicho": nicho, "regiao": regiao, "ttl_horas": ttl_horas,
            "topicos": [{"titulo": "Reels curto", "resumo": "Gancho rápido", "url": ""}],
        }


async def test_planejamento_semanal_duas_etapas_e_bloqueio_orcamento(tmp_path: Path) -> None:
    emp_repo = InMemoryEmpresaRepository()
    conta_repo = InMemoryContaIGRepository()
    cfg_repo = InMemoryConfigIARepository()
    rag_repo = InMemoryRagRepository()
    midia_repo = InMemoryMidiaRepository()
    plano_repo = InMemoryPlanejamentoRepository()
    post_repo = InMemoryPostagemRepository()
    custo_repo = InMemoryCustoRepository()
    storage = LocalStorageAdapter(tmp_path)

    emp = await emp_repo.salvar(Empresa(nome="Studio", limite_mensal_usd=Decimal("5.00")))
    conta = await conta_repo.salvar(
        ContaInstagram(
            empresa_id=emp.id, ig_user_id="7", username="studio_ig",
            access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=20),
        )
    )
    ia = _FakeIAPlano()
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    prompts = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)
    visual = GeradorVisualHibrido(
        midia_repo, storage, ia, orc, FabricaEstrategiasMidia(),
        ProcessadorImagem.compactar_entrada,
    )
    criador = CriarConteudoUseCase(cfg_repo, midia_repo, post_repo, ia, orc, prompts, visual)
    uc = PlanejamentoSemanalUseCase(
        cfg_repo, midia_repo, plano_repo, ia, _FakeTendencias(), orc, prompts, criador
    )

    proposta = await uc.propor_semana(
        ProporPlanejamentoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id,
            semana_inicio=date(2026, 11, 16), quantidade_posts=2,
        )
    )
    assert proposta.status == StatusPlanejamento.AGUARDANDO_APROVACAO
    assert proposta.custo_estimado_usd > Decimal("0")
    assert len(proposta.itens_grade) == 2

    aprovado = await uc.aprovar_plano(emp.id, conta.id, proposta.id)
    assert aprovado.status == StatusPlanejamento.APROVADO

    execucao = await uc.executar_plano(emp.id, conta.id, proposta.id)
    assert execucao.plano.status == StatusPlanejamento.CONCLUIDO
    assert len(execucao.postagens_criadas) == 2
    assert execucao.postagens_criadas[1].legenda == ""
    assert execucao.custo_real_usd == Decimal("0.0840")

    # Se o limite cair abaixo da estimativa, aprovação é bloqueada
    emp.limite_mensal_usd = Decimal("0.01")
    await emp_repo.salvar(emp)
    proposta.status = StatusPlanejamento.AGUARDANDO_APROVACAO
    await plano_repo.salvar(proposta)
    with pytest.raises(ErroOrcamentoExcedido):
        await uc.aprovar_plano(emp.id, conta.id, proposta.id)


async def test_remover_plano_isolamento_e_bloqueio_em_execucao(tmp_path: Path) -> None:
    emp_repo, conta_repo = InMemoryEmpresaRepository(), InMemoryContaIGRepository()
    cfg_repo, rag_repo = InMemoryConfigIARepository(), InMemoryRagRepository()
    midia_repo, plano_repo = InMemoryMidiaRepository(), InMemoryPlanejamentoRepository()
    post_repo, custo_repo = InMemoryPostagemRepository(), InMemoryCustoRepository()
    emp = await emp_repo.salvar(Empresa(nome="Studio Del"))
    conta = await conta_repo.salvar(ContaInstagram(
        empresa_id=emp.id, ig_user_id="8", username="del_ig",
        access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=20),
    ))
    ia = _FakeIAPlano()
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    prompts = ServicoPromptsRagUseCase(conta_repo, cfg_repo, rag_repo)
    visual = GeradorVisualHibrido(
        midia_repo, LocalStorageAdapter(tmp_path), ia, orc, FabricaEstrategiasMidia(),
        ProcessadorImagem.compactar_entrada,
    )
    criador = CriarConteudoUseCase(cfg_repo, midia_repo, post_repo, ia, orc, prompts, visual)
    uc = PlanejamentoSemanalUseCase(
        cfg_repo, midia_repo, plano_repo, ia, _FakeTendencias(), orc, prompts, criador
    )
    plano = await plano_repo.salvar(PlanejamentoSemanal(
        empresa_id=emp.id, conta_ig_id=conta.id, semana_inicio=date(2026, 11, 23),
        status=StatusPlanejamento.EM_EXECUCAO,
    ))
    with pytest.raises(ErroValidacaoDominio):
        await uc.remover_plano(emp.id, conta.id, plano.id)
    plano.status = StatusPlanejamento.AGUARDANDO_APROVACAO
    await plano_repo.salvar(plano)
    assert await uc.remover_plano(emp.id, conta.id, plano.id) is True
    assert await uc.remover_plano(emp.id, conta.id, plano.id) is False
