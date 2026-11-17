"""Testes de integração HTTP para exclusão de planejamento semanal e isolamento multi-tenant."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Configuracoes
from app.dominio.entidades.publicacao import PlanejamentoSemanal
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.objetos_valor.enums_conteudo import StatusPlanejamento
from app.main import criar_app


async def _registrar_e_criar_conta(
    app: FastAPI, cli: AsyncClient, nome_emp: str, email: str, ig_id: str, username: str
) -> tuple[UUID, UUID]:
    reg = await cli.post(
        "/auth/register",
        json={
            "nome_empresa": nome_emp,
            "email": email,
            "senha": "SenhaSuperSegura#1",
            "turnstile_token": "ok",
        },
    )
    assert reg.status_code == 201
    empresa_id = UUID(reg.json()["usuario"]["empresa_id"])
    conta = await app.state.ia_container.conta_repo.salvar(
        ContaInstagram(
            empresa_id=empresa_id,
            ig_user_id=ig_id,
            username=username,
            access_token_enc="tok",
            token_expira_em=datetime.now(UTC) + timedelta(days=30),
        )
    )
    return empresa_id, conta.id


async def test_delete_planejamento_isolamento_multi_tenant_e_status() -> None:
    cfg = Configuracoes(
        app_env="test",
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
    )
    app = criar_app(cfg)
    transport = ASGITransport(app=app)

    async with (
        AsyncClient(transport=transport, base_url="https://testserver") as cli_a,
        AsyncClient(transport=transport, base_url="https://testserver") as cli_b,
    ):
        emp_a, conta_a = await _registrar_e_criar_conta(
            app, cli_a, "Empresa A", "a@emp.com", "1001", "conta_a"
        )
        _, conta_b = await _registrar_e_criar_conta(
            app, cli_b, "Empresa B", "b@emp.com", "1002", "conta_b"
        )
        conta_a2 = await app.state.ia_container.conta_repo.salvar(
            ContaInstagram(
                empresa_id=emp_a,
                ig_user_id="1003",
                username="conta_a2",
                access_token_enc="tok",
                token_expira_em=datetime.now(UTC) + timedelta(days=30),
            )
        )

        plano_repo = app.state.ia_container.plano_repo
        plano = await plano_repo.salvar(
            PlanejamentoSemanal(
                empresa_id=emp_a,
                conta_ig_id=conta_a,
                semana_inicio=date(2026, 11, 16),
                itens_grade=[{"tema": "Post 1"}],
                custo_estimado_usd=Decimal("0.0020"),
                status=StatusPlanejamento.AGUARDANDO_APROVACAO,
            )
        )

        # Outra conta da mesma empresa não pode remover -> 404
        assert (await cli_a.delete(f"/planejamento/{conta_a2.id}/{plano.id}")).status_code == 404
        # Outra empresa não acessa conta_a -> 422 (conta não pertence à empresa B)
        assert (await cli_b.delete(f"/planejamento/{conta_a}/{plano.id}")).status_code == 422
        assert (await cli_b.delete(f"/planejamento/{conta_b}/{plano.id}")).status_code == 404

        # Plano em execução não pode ser removido -> 422
        plano.status = StatusPlanejamento.EM_EXECUCAO
        await plano_repo.salvar(plano)
        assert (await cli_a.delete(f"/planejamento/{conta_a}/{plano.id}")).status_code == 422

        # Concluído pode ser removido -> 204 e desaparece da listagem
        plano.status = StatusPlanejamento.CONCLUIDO
        await plano_repo.salvar(plano)
        assert (await cli_a.delete(f"/planejamento/{conta_a}/{plano.id}")).status_code == 204
        assert (await cli_a.delete(f"/planejamento/{conta_a}/{plano.id}")).status_code == 404
        assert (await cli_a.get(f"/planejamento/{conta_a}")).json() == []
