"""Testes unitários do Diretor de Arte Documental (SceneSpec, séries e anti-repetição)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.aplicacao.ia.diretor_arte import DiretorArteService, sanitizar_prompt_visual
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.dominio.entidades.ia_rag import ConfigIAConta
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram, Empresa
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, TipoMidia
from app.infra.memoria.repo_publicacao_mem import InMemoryCustoRepository
from app.infra.memoria.repo_tenant_mem import InMemoryEmpresaRepository


class _FakeIADiretor:
    def __init__(self, resposta: str | None = None) -> None:
        self.ultimo_system = ""
        self.ultimo_user = ""
        self._resposta = resposta

    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = formato_json
        self.ultimo_system = system_prompt
        self.ultimo_user = user_prompt
        conteudo = self._resposta if self._resposta is not None else json.dumps({
            "sujeito_principal": "Barista vertendo água quente no coador V60",
            "acao_e_narrativa": "movimento lento circular na extração",
            "ambiente": "balcão de madeira rústica da cafeteria",
            "enquadramento_lente": "plano fechado 50mm documental, 8k fullhd",
            "iluminacao": "luz natural da manhã entrando pela vitrine, studio lighting",
            "paleta_e_clima": "tons terrosos acolhedores",
            "evitar": ["mãos extras", "texto borrado"],
            "prompt_imagem_final": (
                "Barista vertendo água no V60 em balcão de madeira, 8k fullhd HDR studio lighting"
            ),
        })
        return conteudo, {
            "openrouter_gen_id": "da-1", "modelo": modelo,
            "tokens_in": 110, "tokens_out": 80, "custo_usd": Decimal("0.0020"),
        }

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        _ = (prompt, modelo, imagem_base_url)
        return b"", {}


def test_sanitizar_prompt_visual_remove_cliches_artificiais() -> None:
    bruto = "Retrato real, 8k fullhd, HDR, studio lighting, unreal engine, luz natural"
    limpo = sanitizar_prompt_visual(bruto)
    for termo in ("8k", "fullhd", "hdr", "studio", "unreal engine"):
        assert termo not in limpo.lower()
    assert "Retrato real" in limpo and "luz natural" in limpo


async def test_diretor_arte_isola_conta_aplica_anti_repeticao_e_modo_serie() -> None:
    emp_repo, custo_repo = InMemoryEmpresaRepository(), InMemoryCustoRepository()
    emp = await emp_repo.salvar(Empresa(nome="Agencia", limite_mensal_usd=Decimal("5.00")))
    conta = ContaInstagram(
        empresa_id=emp.id, ig_user_id="1", username="cafe_aurora",
        access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    cfg = ConfigIAConta(
        empresa_id=emp.id, conta_ig_id=conta.id,
        persona_json={"marca": "Café Aurora", "nicho": "cafeteria artesanal"},
        brand_bible_json={"marca": "Café Aurora", "nicho": "cafeteria",
                          "diretrizes_visuais": "Fotografia quente documental sem filtros"},
    )
    historico = [MidiaBiblioteca(
        empresa_id=emp.id, conta_ig_id=conta.id, pasta=PastaMidia.IA_CRIA,
        chave_storage=f"{emp.id}/{conta.id}/IA-Cria/antiga.jpg",
        tipo_arquivo="image/jpeg", tamanho_bytes=500,
        resumo_visual="Xícara vista de cima na mesa branca",
    )]
    orc = ServicoOrcamentoUseCase(emp_repo, custo_repo)
    fake_ia = _FakeIADiretor()
    diretor = DiretorArteService(fake_ia, orc)

    spec_unico, custo, _ = await diretor.dirigir_cena(
        conta, cfg, "Extração filtrada", "educar", TipoMidia.IMAGE, "4:5",
        "Guia rápido de V60", historico, pilar_editorial="Educação",
        prompt_avancado="Foco nas mãos segurando a chaleira",
    )
    assert custo == Decimal("0.0020")
    assert "Café Aurora" in fake_ia.ultimo_system and "ANTI-REPETIÇÃO" in fake_ia.ultimo_user
    assert "Xícara vista de cima" in fake_ia.ultimo_user
    assert "8k" not in spec_unico.prompt_imagem_final.lower()
    assert "hdr" not in spec_unico.prompt_imagem_final.lower()
    assert "studio" not in spec_unico.prompt_imagem_final.lower()
    assert "chaleira" in spec_unico.prompt_imagem_final.lower()

    spec_serie, _, _ = await diretor.dirigir_cena(
        conta, cfg, "Extração filtrada", "educar", TipoMidia.IMAGE, "4:5",
        "Etapa 2 moagem", historico, modo_serie=True, etapa_serie="2/3 - Moagem",
    )
    assert spec_serie.modo_serie is True and "MODO SÉRIE ATIVO" in fake_ia.ultimo_user
    assert "CONTINUIDADE DE SÉRIE" in fake_ia.ultimo_user


async def test_diretor_arte_fallback_quando_ia_retorna_texto_invalido() -> None:
    emp_repo, custo_repo = InMemoryEmpresaRepository(), InMemoryCustoRepository()
    emp = await emp_repo.salvar(Empresa(nome="Estudio", limite_mensal_usd=Decimal("5.00")))
    conta = ContaInstagram(
        empresa_id=emp.id, ig_user_id="2", username="studio_yoga",
        access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    cfg = ConfigIAConta(empresa_id=emp.id, conta_ig_id=conta.id)
    diretor = DiretorArteService(
        _FakeIADiretor("resposta invalida"), ServicoOrcamentoUseCase(emp_repo, custo_repo)
    )
    spec, _, _ = await diretor.dirigir_cena(
        conta, cfg, "Respiração consciente", "engajar", TipoMidia.IMAGE, "4:5",
        "Aula matinal", [],
    )
    assert "Respiração consciente" in spec.prompt_imagem_final
