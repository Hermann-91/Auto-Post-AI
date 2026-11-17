"""Testes de integração HTTP da Fase 3: curadoria em lote, só-texto, visão e auto-agenda."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core.config import Configuracoes
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.objetos_valor.enums_conteudo import PastaMidia
from app.main import criar_app


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (600, 600), (50, 90, 140)).save(buf, format="JPEG")
    return buf.getvalue()


class _FakeIAHttpFase3:
    async def gerar_texto(
        self, system_prompt: str, user_prompt: str, modelo: str, formato_json: bool = False
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, formato_json)
        if "Planeje" in user_prompt:
            txt = json.dumps({"itens": [
                {"dia_semana": "Segunda", "horario_sugerido": "18:00", "formato": "IMAGE",
                 "tema": "Foto produto", "usar_ia_imagem": True},
                {"dia_semana": "Terça", "horario_sugerido": "19:00", "formato": "REELS",
                 "tema": "Reels roteiro", "usar_ia_imagem": False},
            ]})
        elif "DIREÇÃO DE ARTE" in system_prompt:
            txt = json.dumps({
                "sujeito_principal": "Produto", "acao_e_narrativa": "mesa",
                "ambiente": "loja", "enquadramento_lente": "35mm", "iluminacao": "natural",
                "paleta_e_clima": "quente", "evitar": [], "prompt_imagem_final": "Produto em mesa",
            })
        else:
            txt = json.dumps({"legenda": "Legenda HTTP F3", "hashtags": ["#f3"],
                              "roteiro_slides": []})
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
        _ = (user_prompt, imagem_data_url)
        if "CRÍTICO VISUAL" in system_prompt:
            return json.dumps({
                "anatomia_correta": True, "sem_texto_corrompido": True,
                "realismo_fotografico": True, "aderencia_ao_briefing": True,
                "aprovado": True, "diagnostico_correcao": "",
            }), {"modelo": modelo, "tokens_in": 50, "tokens_out": 20,
                 "custo_usd": Decimal("0.0005")}
        return json.dumps({
            "descricao_visual": "Vitrine iluminada com produto em destaque.",
            "horario_sugerido": "17:45", "justificativa_horario": "Fim de tarde.",
        }), {"modelo": modelo, "tokens_in": 50, "tokens_out": 20, "custo_usd": Decimal("0.0005")}

    async def analisar_multiplas_imagens(
        self, system_prompt: str, user_prompt: str, imagens: Sequence[str], modelo: str
    ) -> tuple[str, dict[str, Any]]:
        _ = (system_prompt, user_prompt, imagens)
        return json.dumps({
            "indice_vencedora": 2, "justificativa": "Melhor enquadramento.", "avaliacoes": [],
        }), {"modelo": modelo, "tokens_in": 80, "tokens_out": 20, "custo_usd": Decimal("0.0010")}


class _FakeTendHttpF3:
    async def buscar_tendencias(
        self, nicho: str, regiao: str, ttl_horas: int = 48
    ) -> dict[str, Any]:
        return {"nicho": nicho, "regiao": regiao, "ttl_horas": ttl_horas, "topicos": []}


async def test_fluxo_http_fase3_curadoria_so_texto_visao_e_auto_agendar(tmp_path: Path) -> None:
    cfg = Configuracoes(
        app_env="test", argon2_time_cost=1, argon2_memory_cost_kib=8192, argon2_parallelism=1,
        storage_local_dir=str(tmp_path / "media"),
    )
    app = criar_app(cfg)
    fake = _FakeIAHttpFase3()
    app.state.ia_container.cliente_ia = fake
    app.state.ia_container.cliente_visao = fake
    app.state.ia_container.tendencias = _FakeTendHttpF3()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as cli:
        reg = await cli.post("/auth/register", json={
            "nome_empresa": "F3 Co", "email": "f3@emp.com",
            "senha": "SenhaSuperSegura#1", "turnstile_token": "ok",
        })
        emp_id = UUID(reg.json()["usuario"]["empresa_id"])
        conta = await app.state.ia_container.conta_repo.salvar(
            ContaInstagram(
                empresa_id=emp_id, ig_user_id="3001", username="f3_ig",
                access_token_enc="tok", token_expira_em=datetime.now(UTC) + timedelta(days=30),
            )
        )
        mids: list[UUID] = []
        for idx in range(2):
            ch = f"{emp_id}/{conta.id}/originais/f{idx}.jpg"
            await app.state.ia_container.storage.enviar_bytes(ch, _jpeg_bytes(), "image/jpeg")
            m = await app.state.ia_container.midia_repo.salvar(
                MidiaBiblioteca(
                    empresa_id=emp_id, conta_ig_id=conta.id, pasta=PastaMidia.ORIGINAIS,
                    chave_storage=ch, tipo_arquivo="image/jpeg", tamanho_bytes=500,
                )
            )
            mids.append(m.id)

        cur = await cli.post(
            f"/ia/curadoria/{conta.id}/eleger-melhor",
            json={"midia_ids": [str(m) for m in mids], "objetivo_contexto": "Engajamento"},
        )
        assert cur.status_code == 200 and cur.json()["indice_vencedora"] == 2

        rasc = await cli.post("/posts", json={
            "conta_ig_id": str(conta.id), "tipo_midia": "IMAGE", "legenda": "Só texto",
        })
        assert rasc.status_code == 201 and rasc.json()["midias_chaves"] == []
        pid = rasc.json()["id"]
        assert (await cli.post(
            f"/posts/{conta.id}/{pid}/agendar", json={"agendado_para": "2027-01-10T18:00:00Z"}
        )).status_code == 422

        anex = await cli.patch(
            f"/posts/{conta.id}/{pid}/midias", json={"midia_ids": [str(mids[0])]}
        )
        assert anex.status_code == 200 and len(anex.json()["midias_chaves"]) == 1
        assert (await cli.post(
            f"/posts/{conta.id}/{pid}/agendar", json={"agendado_para": "2027-01-10T18:00:00Z"}
        )).status_code == 200

        vis = await cli.post("/ia/criar", json={
            "conta_ig_id": str(conta.id), "tipo_midia": "IMAGE",
            "tema": "Foto vitrine", "midia_base_ids": [str(mids[0])], "gerar_imagem_ia": False,
        })
        assert vis.status_code == 200 and vis.json()["horario_sugerido"] == "17:45"

        prop = await cli.post("/planejamento/propor", json={
            "conta_ig_id": str(conta.id), "semana_inicio": "2027-02-01",
            "composicao_formatos": {"IMAGE": 1, "REELS": 1}, "auto_agendar": True,
        })
        assert prop.status_code == 201
        plano_id = prop.json()["id"]
        assert (await cli.post(f"/planejamento/{conta.id}/{plano_id}/aprovar")).status_code == 200
        exec_r = await cli.post(f"/planejamento/{conta.id}/{plano_id}/executar")
        assert exec_r.status_code == 200
        criados = exec_r.json()["postagens_criadas"]
        assert criados[0]["status"] == "AGENDADO" and criados[1]["status"] == "RASCUNHO"
