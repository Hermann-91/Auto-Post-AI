"""Testes unitários do GeradorVisualHibrido: loop máx 2 iterações e múltiplas referências."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.aplicacao.ia.dtos import CriarConteudoCmd
from app.aplicacao.ia.dtos_visuais import SceneSpec
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.dominio.entidades.ia_rag import ConfigIAConta
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, TipoMidia
from app.infra.memoria.repo_conteudo_mem import InMemoryMidiaRepository
from app.infra.memoria.repo_publicacao_mem import InMemoryCustoRepository
from app.infra.memoria.repo_tenant_mem import InMemoryEmpresaRepository
from app.infra.midia.estrategias_midia import FabricaEstrategiasMidia
from app.infra.midia.processador_imagem import ProcessadorImagem
from app.infra.storage.local_storage_adapter import LocalStorageAdapter


def _jpeg_teste() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (800, 800), (140, 100, 60)).save(buf, format="JPEG")
    return buf.getvalue()


class _FakeIAMultiRef:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.refs_recebidas: list[list[str]] = []

    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, modelo, formato_json)
        return "{}", {}

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        self.prompts.append(prompt)
        self.refs_recebidas.append([imagem_base_url] if imagem_base_url else [])
        return _jpeg_teste(), {
            "openrouter_gen_id": f"img-{len(self.prompts)}", "modelo": modelo,
            "tokens_in": 40, "tokens_out": 800, "custo_usd": Decimal("0.0400"),
        }

    async def gerar_imagem_com_referencias(
        self, prompt: str, modelo: str, imagens_base_urls: Sequence[str]
    ) -> tuple[bytes, dict[str, Any]]:
        self.prompts.append(prompt)
        self.refs_recebidas.append(list(imagens_base_urls))
        return _jpeg_teste(), {
            "openrouter_gen_id": f"mref-{len(self.prompts)}", "modelo": modelo,
            "tokens_in": 60, "tokens_out": 800, "custo_usd": Decimal("0.0400"),
        }


class _FakeCriticoSequencial:
    def __init__(self, vereditos: list[tuple[bool, str]]) -> None:
        self._vereditos = list(vereditos)
        self.chamadas = 0

    async def analisar_imagem(
        self, system_prompt: str, user_prompt: str, imagem_data_url: str, modelo: str
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, imagem_data_url)
        aprovado, diag = self._vereditos[min(self.chamadas, len(self._vereditos) - 1)]
        self.chamadas += 1
        return json.dumps({
            "anatomia_correta": aprovado, "sem_texto_corrompido": True,
            "realismo_fotografico": True, "aderencia_ao_briefing": True,
            "aprovado": aprovado, "diagnostico_correcao": diag,
        }), {
            "openrouter_gen_id": f"vis-{self.chamadas}", "modelo": modelo,
            "tokens_in": 100, "tokens_out": 30, "custo_usd": Decimal("0.0015"),
        }


async def test_loop_corrige_na_segunda_iteracao_e_limita_em_dois(tmp_path: Path) -> None:
    emp_repo, custo_repo = InMemoryEmpresaRepository(), InMemoryCustoRepository()
    midia_repo, storage = InMemoryMidiaRepository(), LocalStorageAdapter(tmp_path)
    emp = await emp_repo.salvar(Empresa(nome="Padaria", limite_mensal_usd=Decimal("5.00")))
    conta = ContaInstagram(
        empresa_id=emp.id, ig_user_id="1", username="padaria_real",
        access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    cfg = ConfigIAConta(empresa_id=emp.id, conta_ig_id=conta.id)
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    ia = _FakeIAMultiRef()
    visao_corrige = _FakeCriticoSequencial([(False, "Corrigir dedos da mão"), (True, "")])
    gerador = GeradorVisualHibrido(
        midia_repo, storage, ia, orc, FabricaEstrategiasMidia(),
        ProcessadorImagem.compactar_entrada, cliente_visao=visao_corrige,
    )
    spec = SceneSpec(
        sujeito_principal="Padeiro segurando pão", acao_e_narrativa="saindo do forno",
        ambiente="padaria", enquadramento_lente="35mm", iluminacao="luz da manhã",
        paleta_e_clima="quente", prompt_imagem_final="Padeiro com pão, 8k fullhd HDR studio",
    )
    res = await gerador.gerar_e_persistir_com_revisao(
        CriarConteudoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
            tema="Pão quente", gerar_imagem_ia=True, presets_melhoria=("fullhd", "iluminacao"),
        ),
        cfg, spec.prompt_imagem_final, scene_spec=spec,
    )
    assert res.qualidade_revisao.aprovado is True
    assert res.qualidade_revisao.tentativas_geracao == 2
    assert res.qualidade_revisao.revisoes_critico == 2
    assert "Corrigir dedos da mão" in ia.prompts[1]
    assert "8k" not in res.prompt_final_usado.lower()
    assert "studio" not in res.prompt_final_usado.lower()
    assert res.midia.resumo_visual == spec.resumo_anti_repeticao()
    assert res.custo_total_usd == Decimal("0.0830")

    visao_sempre_fail = _FakeCriticoSequencial([(False, "Erro 1"), (False, "Erro 2")])
    gerador_limite = GeradorVisualHibrido(
        midia_repo, storage, _FakeIAMultiRef(), orc, FabricaEstrategiasMidia(),
        ProcessadorImagem.compactar_entrada, cliente_visao=visao_sempre_fail,
    )
    res_fail = await gerador_limite.gerar_e_persistir_com_revisao(
        CriarConteudoCmd(
            empresa_id=emp.id, conta_ig_id=conta.id, tipo_midia=TipoMidia.IMAGE,
            tema="Teste limite", gerar_imagem_ia=True,
        ),
        cfg, "Cena simples",
    )
    assert res_fail.qualidade_revisao.aprovado is False
    assert res_fail.qualidade_revisao.tentativas_geracao == 2 and visao_sempre_fail.chamadas == 2


async def test_multiplas_referencias_reais_e_isolamento_entre_contas(tmp_path: Path) -> None:
    emp_repo, custo_repo = InMemoryEmpresaRepository(), InMemoryCustoRepository()
    midia_repo, storage = InMemoryMidiaRepository(), LocalStorageAdapter(tmp_path)
    emp = await emp_repo.salvar(Empresa(nome="Marca", limite_mensal_usd=Decimal("5.00")))
    conta_a = ContaInstagram(
        empresa_id=emp.id, ig_user_id="1", username="conta_a",
        access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    conta_b = ContaInstagram(
        empresa_id=emp.id, ig_user_id="2", username="conta_b",
        access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    refs = []
    for i in range(2):
        chave = f"{emp.id}/{conta_a.id}/originais/ref_{i}.jpg"
        await storage.enviar_bytes(chave, _jpeg_teste(), "image/jpeg")
        refs.append(await midia_repo.salvar(MidiaBiblioteca(
            empresa_id=emp.id, conta_ig_id=conta_a.id, pasta=PastaMidia.ORIGINAIS,
            chave_storage=chave, tipo_arquivo="image/jpeg", tamanho_bytes=1200,
        )))
    chave_b = f"{emp.id}/{conta_b.id}/originais/b.jpg"
    await storage.enviar_bytes(chave_b, _jpeg_teste(), "image/jpeg")
    ref_b = await midia_repo.salvar(MidiaBiblioteca(
        empresa_id=emp.id, conta_ig_id=conta_b.id, pasta=PastaMidia.ORIGINAIS,
        chave_storage=chave_b, tipo_arquivo="image/jpeg", tamanho_bytes=1200,
    ))

    ia = _FakeIAMultiRef()
    gerador = GeradorVisualHibrido(
        midia_repo, storage, ia, ServicoOrcamentoUseCase(emp_repo, custo_repo),
        FabricaEstrategiasMidia(), ProcessadorImagem.compactar_entrada,
    )
    cfg = ConfigIAConta(empresa_id=emp.id, conta_ig_id=conta_a.id)
    await gerador.gerar_e_persistir_com_revisao(
        CriarConteudoCmd(
            empresa_id=emp.id, conta_ig_id=conta_a.id, tipo_midia=TipoMidia.IMAGE,
            tema="Produto real", gerar_imagem_ia=True, midia_base_ids=(refs[0].id, refs[1].id),
        ),
        cfg, "Produto real em mesa de cozinha",
    )
    assert len(ia.refs_recebidas[0]) == 2

    with pytest.raises(ErroValidacaoDominio):
        await gerador.gerar_e_persistir_com_revisao(
            CriarConteudoCmd(
                empresa_id=emp.id, conta_ig_id=conta_a.id, tipo_midia=TipoMidia.IMAGE,
                tema="Invasão", gerar_imagem_ia=True, midia_base_ids=(ref_b.id,),
            ),
            cfg, "Cena",
        )
