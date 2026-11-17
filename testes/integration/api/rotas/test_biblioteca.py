"""Testes de integração HTTP das rotas /biblioteca/* com cota, curtidas e limpeza."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core.config import Configuracoes
from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem, TipoMidia
from app.main import criar_app


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (800, 800), (20, 140, 190)).save(buf, format="PNG")
    return buf.getvalue()


async def _criar_tenant_com_conta(cli: AsyncClient, app: object, email: str) -> tuple[UUID, UUID]:
    reg = await cli.post(
        "/auth/register",
        json={
            "nome_empresa": f"Empresa {email}",
            "email": email,
            "senha": "SenhaSuperSegura#1",
            "turnstile_token": "ok",
        },
    )
    assert reg.status_code == 201
    empresa_id = UUID(reg.json()["usuario"]["empresa_id"])
    conta = await app.state.ia_container.conta_repo.salvar(  # type: ignore[attr-defined]
        ContaInstagram(
            empresa_id=empresa_id,
            ig_user_id=f"ig-{empresa_id.hex[:8]}",
            username=f"user_{empresa_id.hex[:6]}",
            access_token_enc="tok",
            token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    return empresa_id, conta.id


async def test_fluxo_biblioteca_upload_curtida_limpeza_e_anti_idor(tmp_path: Path) -> None:
    cfg = Configuracoes(
        app_env="test",
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
        storage_local_dir=str(tmp_path / "media"),
    )
    app = criar_app(cfg)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://testserver") as cli_a:
        emp_a, conta_a = await _criar_tenant_com_conta(cli_a, app, "bib_a@emp.com")

        up1 = await cli_a.post(
            f"/biblioteca/{conta_a}/upload",
            data={"pasta": "originais", "resumo_visual": "Foto principal"},
            files={"arquivo": ("foto1.png", _png_bytes(), "image/png")},
        )
        assert up1.status_code == 201
        m1 = up1.json()
        assert m1["tipo_arquivo"] == "image/jpeg"

        up2 = await cli_a.post(
            f"/biblioteca/{conta_a}/upload",
            data={"pasta": "processadas"},
            files={"arquivo": ("foto2.png", _png_bytes(), "image/png")},
        )
        assert up2.status_code == 201
        m2 = up2.json()

        cota = await cli_a.get(f"/biblioteca/{conta_a}/cota")
        assert cota.status_code == 200 and cota.json()["itens_usados"] == 2

        orig = await cli_a.get(f"/biblioteca/{conta_a}?pasta=originais")
        assert orig.status_code == 200 and len(orig.json()) == 1

        prev = await cli_a.get(f"/biblioteca/{conta_a}/midias/{m1['id']}/conteudo")
        assert prev.status_code == 200 and prev.content.startswith(b"\xff\xd8")

        curtida = await cli_a.patch(
            f"/biblioteca/{conta_a}/{m1['id']}/curtida",
            json={"favorita": True},
        )
        assert curtida.status_code == 200 and curtida.json()["curtida_favorita"] is True

        # Marca ambas como usadas em posts já PUBLICADOS; limpeza deve remover só m2
        for ch in (m1["chave_storage"], m2["chave_storage"]):
            await app.state.ia_container.post_repo.salvar(
                Postagem(
                    empresa_id=emp_a,
                    conta_ig_id=conta_a,
                    tipo_midia=TipoMidia.IMAGE,
                    midias_chaves=[ch],
                    legenda="Publicado",
                    status=StatusPostagem.PUBLICADO,
                )
            )

        limp = await cli_a.post(f"/biblioteca/{conta_a}/limpar-pos-postagem")
        assert limp.status_code == 200
        assert limp.json()["removidas_qtd"] == 1
        assert limp.json()["chaves_removidas"] == [m2["chave_storage"]]

        invalido = await cli_a.post(
            f"/biblioteca/{conta_a}/upload",
            data={"pasta": "originais"},
            files={"arquivo": ("script.txt", b"oi", "text/plain")},
        )
        assert invalido.status_code == 422

        up3 = await cli_a.post(
            f"/biblioteca/{conta_a}/upload",
            data={"pasta": "originais"},
            files={"arquivo": ("foto3.png", _png_bytes(), "image/png")},
        )
        assert up3.status_code == 201
        assert (await cli_a.delete(f"/biblioteca/{conta_a}/{up3.json()['id']}")).status_code == 200

    async with AsyncClient(transport=transport, base_url="https://testserver") as cli_b:
        await _criar_tenant_com_conta(cli_b, app, "bib_b@emp.com")
        assert (await cli_b.get(f"/biblioteca/{conta_a}")).status_code == 422
        assert (await cli_b.post(f"/biblioteca/{conta_a}/limpar-pos-postagem")).status_code == 422
        assert (await cli_b.delete(f"/biblioteca/{conta_a}/{m1['id']}")).status_code == 422
