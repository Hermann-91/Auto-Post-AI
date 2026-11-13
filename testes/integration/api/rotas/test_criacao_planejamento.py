"""Testes de integração HTTP das rotas de ConfigIA/RAG, Criação IA e Planejamento."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from PIL import Image

from app.core.config import Configuracoes
from app.dominio.entidades.tenant import ContaInstagram
from app.main import criar_app


def _png_teste() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (640, 640), (30, 110, 180)).save(buf, format="PNG")
    return buf.getvalue()


class _FakeGatewayOpenRouter:
    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, formato_json)
        if "Planeje" in user_prompt:
            txt = json.dumps(
                {
                    "itens": [
                        {
                            "dia_semana": "Terça", "formato": "IMAGE", "tema": "Bastidores",
                            "objetivo": "autoridade", "ideia_visual": "Estúdio iluminado",
                            "usar_ia_imagem": True,
                        }
                    ]
                }
            )
        else:
            txt = json.dumps(
                {
                    "legenda": "Legenda da API", "hashtags": ["#marca"],
                    "prompt_visual": "Foto clean", "roteiro_slides": [],
                }
            )
        return txt, {
            "openrouter_gen_id": "g-api-txt", "modelo": modelo,
            "tokens_in": 100, "tokens_out": 50, "custo_usd": Decimal("0.0020"),
        }

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        _ = (prompt, imagem_base_url)
        return _png_teste(), {
            "openrouter_gen_id": "g-api-img", "modelo": modelo,
            "tokens_in": 50, "tokens_out": 900, "custo_usd": Decimal("0.0300"),
        }

    async def analisar_imagem(
        self, system_prompt: str, user_prompt: str, imagem_data_url: str, modelo: str
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, imagem_data_url)
        return "Composição limpa em tons frios.", {
            "openrouter_gen_id": "g-api-vis", "modelo": modelo,
            "tokens_in": 90, "tokens_out": 15, "custo_usd": Decimal("0.0005"),
        }


class _FakeTendenciasAPI:
    async def buscar_tendencias(
        self, nicho: str, regiao: str, ttl_horas: int = 48
    ) -> dict[str, Any]:
        return {
            "nicho": nicho, "regiao": regiao, "ttl_horas": ttl_horas,
            "cache_hit": False, "topicos": [{"titulo": "Tendência", "resumo": "Reels"}],
        }


async def _preparar_sessao_e_conta(app: FastAPI, client: AsyncClient) -> tuple[UUID, UUID]:
    reg = await client.post(
        "/auth/register",
        json={
            "nome_empresa": "Agencia HTTP",
            "email": "dono@agencia.com",
            "senha": "SenhaSuperSegura#1",
            "turnstile_token": "ok",
        },
    )
    assert reg.status_code == 201
    empresa_id = UUID(reg.json()["usuario"]["empresa_id"])

    ia_box = app.state.ia_container
    fake_ia = _FakeGatewayOpenRouter()
    ia_box.cliente_ia = fake_ia
    ia_box.cliente_visao = fake_ia
    ia_box.tendencias = _FakeTendenciasAPI()

    conta = await ia_box.conta_repo.salvar(
        ContaInstagram(
            empresa_id=empresa_id,
            ig_user_id="888777",
            username="agencia_oficial",
            access_token_enc="enc_tok",
            token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    return empresa_id, conta.id


async def test_fluxo_http_config_rag_criacao_curadoria_e_planejamento(tmp_path: Path) -> None:
    cfg = Configuracoes(
        app_env="test",
        cors_origens=["https://painel.exemplo.com"],
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
        storage_local_dir=str(tmp_path / "media"),
    )
    app = criar_app(cfg)

    from httpx import ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as cli:
        empresa_id, conta_id = await _preparar_sessao_e_conta(app, cli)

        contas = await cli.get("/contas")
        assert contas.status_code == 200 and contas.json()[0]["username"] == "agencia_oficial"

        up_cfg = await cli.put(
            f"/contas/{conta_id}/ia-config",
            json={
                "persona_json": {"marca": "Agência HTTP", "nicho": "arquitetura"},
                "templates_json": {},
                "aplicar_logo_padrao": False,
                "modelo_texto_pref": "deepseek/deepseek-v4-flash",
                "modelo_img_pref": "google/gemini-3.1-flash-image",
            },
        )
        assert up_cfg.status_code == 200

        rag = await cli.post(
            f"/contas/{conta_id}/rag",
            json={"tipo": "FAQ", "titulo": "Serviços", "conteudo": "Projetos residenciais."},
        )
        assert rag.status_code == 201
        fonte_id = rag.json()["id"]

        criado = await cli.post(
            "/ia/criar",
            json={"conta_ig_id": str(conta_id), "tipo_midia": "IMAGE", "tema": "Sala minimalista",
                  "gerar_imagem_ia": True},
        )
        assert criado.status_code == 200
        body = criado.json()
        assert body["postagem"]["status"] == "RASCUNHO"
        midia_id = body["midias_geradas"][0]["id"]

        cur = await cli.post(f"/ia/curadoria/{conta_id}/{midia_id}")
        assert cur.status_code == 200 and "Composição limpa" in cur.json()["resumo_visual"]

        prop = await cli.post(
            "/planejamento/propor",
            json={"conta_ig_id": str(conta_id), "semana_inicio": "2026-11-16",
                  "quantidade_posts": 1},
        )
        assert prop.status_code == 201
        plano_id = prop.json()["id"]
        assert prop.json()["status"] == "AGUARDANDO_APROVACAO"

        aprov = await cli.post(f"/planejamento/{conta_id}/{plano_id}/aprovar")
        assert aprov.status_code == 200 and aprov.json()["status"] == "APROVADO"

        exec_resp = await cli.post(f"/planejamento/{conta_id}/{plano_id}/executar")
        assert exec_resp.status_code == 200
        assert exec_resp.json()["plano"]["status"] == "CONCLUIDO"
        assert len(exec_resp.json()["postagens_criadas"]) == 1

        orc = await cli.get(f"/contas/{conta_id}/orcamento")
        assert orc.status_code == 200 and Decimal(str(orc.json()["gasto_conta_usd"])) > 0

        # Remoção RAG e bloqueio de orçamento 402
        assert (await cli.delete(f"/contas/{conta_id}/rag/{fonte_id}")).status_code == 204
        emp = await app.state.auth_container.empresa_repo.buscar_por_id(empresa_id)
        assert emp is not None
        emp.limite_mensal_usd = Decimal("0.001")
        await app.state.auth_container.empresa_repo.salvar(emp)
        bloq = await cli.post(
            "/ia/criar",
            json={"conta_ig_id": str(conta_id), "tipo_midia": "IMAGE", "tema": "Bloqueado"},
        )
        assert bloq.status_code == 402
