"""Testes de integração HTTP para Jobs Assíncronos de IA e isolamento multi-tenant."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core.config import Configuracoes
from app.dominio.entidades.tenant import ContaInstagram
from app.main import criar_app


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (600, 600), (40, 120, 160)).save(buf, format="JPEG")
    return buf.getvalue()


class _FakeIAJobs:
    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = formato_json
        if "Planeje" in user_prompt:
            txt = json.dumps({"itens": [
                {"dia_semana": "Segunda", "horario_sugerido": "18:00", "formato": "IMAGE",
                 "tema": "Bastidores 1", "usar_ia_imagem": True},
                {"dia_semana": "Terça", "horario_sugerido": "19:00", "formato": "REELS",
                 "tema": "Roteiro 2", "usar_ia_imagem": False},
            ]})
        elif "DIREÇÃO DE ARTE" in system_prompt:
            txt = json.dumps({
                "sujeito_principal": "Artesã", "acao_e_narrativa": "trabalhando",
                "ambiente": "ateliê", "enquadramento_lente": "35mm", "iluminacao": "natural",
                "paleta_e_clima": "quente", "evitar": [], "prompt_imagem_final": "Ateliê natural",
            })
        else:
            txt = json.dumps({
                "legenda": "Legenda gerada por Job", "hashtags": ["#job"], "roteiro_slides": [],
            })
        return txt, {"modelo": modelo, "tokens_in": 40, "tokens_out": 20,
                     "custo_usd": Decimal("0.0020")}

    async def gerar_ou_editar_imagem(
        self, prompt: str, modelo: str, imagem_base_url: str | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        _ = (prompt, imagem_base_url)
        return _jpeg_bytes(), {"modelo": modelo, "tokens_in": 20, "tokens_out": 200,
                               "custo_usd": Decimal("0.0200")}

    async def analisar_imagem(
        self, system_prompt: str, user_prompt: str, imagem_data_url: str, modelo: str
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, imagem_data_url)
        return json.dumps({
            "anatomia_correta": True, "sem_texto_corrompido": True,
            "realismo_fotografico": True, "aderencia_ao_briefing": True,
            "aprovado": True, "diagnostico_correcao": "",
        }), {"modelo": modelo, "tokens_in": 40, "tokens_out": 15, "custo_usd": Decimal("0.0005")}


class _FakeTendJobs:
    async def buscar_tendencias(
        self, nicho: str, regiao: str, ttl_horas: int = 48
    ) -> dict[str, Any]:
        return {"nicho": nicho, "regiao": regiao, "ttl_horas": ttl_horas, "topicos": []}


async def _aguardar_job(cli: AsyncClient, job_id: str) -> dict[str, Any]:
    for _ in range(50):
        resp = await cli.get(f"/ia/jobs/{job_id}")
        assert resp.status_code == 200
        dados = resp.json()
        if dados["status"] in {"CONCLUIDO", "FALHA"}:
            return dict(dados)
        await asyncio.sleep(0.02)
    raise AssertionError("Job não finalizou dentro do tempo esperado.")


async def test_jobs_ia_ciclo_completo_idempotencia_e_isolamento(tmp_path: Path) -> None:
    cfg = Configuracoes(
        app_env="test", argon2_time_cost=1, argon2_memory_cost_kib=8192, argon2_parallelism=1,
        storage_local_dir=str(tmp_path / "media"),
    )
    app = criar_app(cfg)
    fake = _FakeIAJobs()
    app.state.ia_container.cliente_ia = fake
    app.state.ia_container.cliente_visao = fake
    app.state.ia_container.tendencias = _FakeTendJobs()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://t") as cli_a:
        reg_a = await cli_a.post("/auth/register", json={
            "nome_empresa": "Jobs Co", "email": "jobs@a.com",
            "senha": "SenhaSuperSegura#1", "turnstile_token": "ok",
        })
        emp_a = UUID(reg_a.json()["usuario"]["empresa_id"])
        conta_a = await app.state.ia_container.conta_repo.salvar(
            ContaInstagram(
                empresa_id=emp_a, ig_user_id="4001", username="jobs_a",
                access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
            )
        )

        # 1. Criação unitária só-texto via job + idempotência contra duplo clique
        req_criar = {
            "conta_ig_id": str(conta_a.id), "tipo_job": "CRIAR_CONTEUDO",
            "chave_idempotencia": "duplo-1",
            "criar_conteudo": {
                "conta_ig_id": str(conta_a.id), "tipo_midia": "IMAGE",
                "tema": "Post só texto", "gerar_imagem_ia": False, "salvar_rascunho": True,
            },
        }
        j1 = await cli_a.post("/ia/jobs", json=req_criar)
        j2 = await cli_a.post("/ia/jobs", json=req_criar)
        assert j1.status_code == 202 and j2.status_code == 202
        assert j1.json()["id"] == j2.json()["id"]
        res_criar = await _aguardar_job(cli_a, j1.json()["id"])
        assert res_criar["status"] == "CONCLUIDO" and res_criar["percentual"] == 100
        post_id = res_criar["resultado_json"]["postagem"]["id"]
        assert res_criar["resultado_json"]["postagem"]["midias_chaves"] == []

        # 2. Botão rápido "Mais natural" / Gerar imagem no card via RECRIAR_POSTAGEM
        j_rec = await cli_a.post("/ia/jobs", json={
            "conta_ig_id": str(conta_a.id), "tipo_job": "RECRIAR_POSTAGEM",
            "recriar_postagem": {
                "postagem_id": post_id, "alvo": "imagem", "contexto_adicional": "Mais natural",
            },
        })
        assert j_rec.status_code == 202
        res_rec = await _aguardar_job(cli_a, j_rec.json()["id"])
        assert res_rec["status"] == "CONCLUIDO"
        assert len(res_rec["resultado_json"]["midias_chaves"]) == 1

        # 3. Grade semanal em 2 etapas via PROPOR_PLANO + EXECUTAR_PLANO (X/Y)
        j_prop = await cli_a.post("/ia/jobs", json={
            "conta_ig_id": str(conta_a.id), "tipo_job": "PROPOR_PLANO",
            "propor_plano": {
                "conta_ig_id": str(conta_a.id), "semana_inicio": "2027-03-01",
                "composicao_formatos": {"IMAGE": 1, "REELS": 1}, "incluir_imagens_ia": True,
            },
        })
        res_prop = await _aguardar_job(cli_a, j_prop.json()["id"])
        assert res_prop["status"] == "CONCLUIDO"
        plano_id = res_prop["resultado_json"]["id"]

        j_exec = await cli_a.post("/ia/jobs", json={
            "conta_ig_id": str(conta_a.id), "tipo_job": "EXECUTAR_PLANO",
            "executar_plano": {"plano_id": plano_id},
        })
        res_exec = await _aguardar_job(cli_a, j_exec.json()["id"])
        assert res_exec["status"] == "CONCLUIDO" and res_exec["progresso_total"] == 2
        assert len(res_exec["resultado_json"]["postagens_criadas"]) == 2

        # 4. Erro de domínio (orçamento estourado) transita job para FALHA
        emp_obj = await app.state.auth_container.empresa_repo.buscar_por_id(emp_a)
        assert emp_obj is not None
        emp_obj.limite_mensal_usd = Decimal("0.001")
        await app.state.auth_container.empresa_repo.salvar(emp_obj)
        j_falha = await cli_a.post("/ia/jobs", json={
            "conta_ig_id": str(conta_a.id), "tipo_job": "CRIAR_CONTEUDO",
            "criar_conteudo": {"conta_ig_id": str(conta_a.id), "tipo_midia": "IMAGE",
                               "tema": "Sem saldo"},
        })
        res_falha = await _aguardar_job(cli_a, j_falha.json()["id"])
        assert res_falha["status"] == "FALHA" and res_falha["erro_detalhe"]

        # 5. Validação payload mismatch -> 422
        assert (await cli_a.post("/ia/jobs", json={
            "conta_ig_id": str(conta_a.id), "tipo_job": "CRIAR_CONTEUDO",
        })).status_code == 422

        job_id_a = j1.json()["id"]

    # 6. Isolamento estrito entre empresas
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://t") as cli_b:
        await cli_b.post("/auth/register", json={
            "nome_empresa": "Outra Co", "email": "b@b.com",
            "senha": "SenhaSuperSegura#1", "turnstile_token": "ok",
        })
        assert (await cli_b.get(f"/ia/jobs/{job_id_a}")).status_code == 404
        assert (await cli_b.get(f"/ia/jobs?conta_ig_id={conta_a.id}")).status_code == 422
