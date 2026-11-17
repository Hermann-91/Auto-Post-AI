"""Testes de integração HTTP das rotas /posts/* com isolamento multi-tenant."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from httpx import ASGITransport, AsyncClient

from app.core.config import Configuracoes
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, TipoMidia
from app.main import criar_app


class _FakeEstrategiaHTTP:
    tipo_suportado = TipoMidia.IMAGE

    async def publicar(
        self,
        conta: ContaInstagram,
        token_descriptografado: str,
        postagem: Postagem,
        urls_publicas: list[str],
    ) -> tuple[str, str]:
        _ = (conta, token_descriptografado, postagem, urls_publicas)
        return "ig_media_http_1", "ig_cont_http_1"


class _FakeFabricaHTTP:
    def obter(self, tipo_midia: TipoMidia) -> _FakeEstrategiaHTTP:
        _ = tipo_midia
        return _FakeEstrategiaHTTP()


async def test_fluxo_http_posts_agendamento_publicacao_e_isolamento(tmp_path: Path) -> None:
    cfg = Configuracoes(
        app_env="test",
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
        storage_local_dir=str(tmp_path / "media"),
    )
    app = criar_app(cfg)
    app.state.meta_container.fabrica_publicadores = _FakeFabricaHTTP()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as cli_a:
        reg_a = await cli_a.post(
            "/auth/register",
            json={
                "nome_empresa": "Tenant A", "email": "a@emp.com",
                "senha": "SenhaSuperSegura#1", "turnstile_token": "ok",
            },
        )
        emp_a = UUID(reg_a.json()["usuario"]["empresa_id"])
        token_enc = app.state.meta_container.cripto.criptografar("tok_a")
        conta_a = await app.state.ia_container.conta_repo.salvar(
            ContaInstagram(
                empresa_id=emp_a, ig_user_id="7001", username="conta_a",
                access_token_enc=token_enc, token_expira_em=datetime.now(UTC) + timedelta(days=30),
            )
        )
        midia_a = await app.state.ia_container.midia_repo.salvar(
            MidiaBiblioteca(
                empresa_id=emp_a, conta_ig_id=conta_a.id, pasta=PastaMidia.IA_CRIA,
                chave_storage=f"{emp_a}/{conta_a.id}/IA-Cria/p.jpg",
                tipo_arquivo="image/jpeg", tamanho_bytes=900,
            )
        )

        criada = await cli_a.post(
            "/posts",
            json={
                "conta_ig_id": str(conta_a.id), "tipo_midia": "IMAGE",
                "midia_ids": [str(midia_a.id)], "legenda": "Post HTTP",
            },
        )
        assert criada.status_code == 201 and criada.json()["status"] == "RASCUNHO"
        post_id = criada.json()["id"]

        ed = await cli_a.patch(
            f"/posts/{conta_a.id}/{post_id}/legenda", json={"legenda": "Legenda editada $0"}
        )
        assert ed.status_code == 200 and ed.json()["legenda"] == "Legenda editada $0"

        ag = await cli_a.post(
            f"/posts/{conta_a.id}/{post_id}/agendar",
            json={"agendado_para": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        )
        assert ag.status_code == 200 and ag.json()["status"] == "AGENDADO"

        pub = await cli_a.post(f"/posts/{conta_a.id}/{post_id}/publicar-agora")
        assert pub.status_code == 200
        assert pub.json()["publicada"] is True
        assert pub.json()["postagem"]["meta_media_id"] == "ig_media_http_1"

        assert (await cli_a.post(f"/posts/{conta_a.id}/{post_id}/cancelar")).status_code == 422
        assert (await cli_a.patch(
            f"/posts/{conta_a.id}/{post_id}/legenda", json={"legenda": "Bloqueado"}
        )).status_code == 422

        rascunho2 = await cli_a.post(
            "/posts",
            json={
                "conta_ig_id": str(conta_a.id), "tipo_midia": "IMAGE",
                "midia_ids": [str(midia_a.id)], "legenda": "Cancelar",
            },
        )
        p2_id = rascunho2.json()["id"]
        canc = await cli_a.post(f"/posts/{conta_a.id}/{p2_id}/cancelar")
        assert canc.status_code == 200 and canc.json()["status"] == "CANCELADO"

        m_excl = await app.state.ia_container.midia_repo.salvar(
            MidiaBiblioteca(
                empresa_id=emp_a, conta_ig_id=conta_a.id, pasta=PastaMidia.IA_CRIA,
                chave_storage=f"{emp_a}/{conta_a.id}/IA-Cria/excl.jpg",
                tipo_arquivo="image/jpeg", tamanho_bytes=500,
            )
        )
        p3 = await cli_a.post(
            "/posts",
            json={"conta_ig_id": str(conta_a.id), "tipo_midia": "IMAGE",
                  "midia_ids": [str(m_excl.id)], "legenda": "Excluir"},
        )
        exc = await cli_a.delete(f"/posts/{conta_a.id}/{p3.json()['id']}")
        assert exc.status_code == 200 and exc.json()["midias_removidas_qtd"] == 1
        assert await app.state.ia_container.midia_repo.buscar_por_id(
            emp_a, conta_a.id, m_excl.id
        ) is None

    async with AsyncClient(transport=transport, base_url="https://testserver") as cli_b:
        await cli_b.post(
            "/auth/register",
            json={
                "nome_empresa": "Tenant B", "email": "b@emp.com",
                "senha": "SenhaSuperSegura#1", "turnstile_token": "ok",
            },
        )
        assert (await cli_b.get(f"/posts/{conta_a.id}")).status_code == 422
        assert (await cli_b.delete(f"/posts/{conta_a.id}/{post_id}")).status_code == 422
