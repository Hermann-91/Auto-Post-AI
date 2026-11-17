"""Repositórios em memória para planejamentos, postagens e custos de IA."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.dominio.entidades.ia_rag import RegistroCustoIA
from app.dominio.entidades.publicacao import PlanejamentoSemanal, Postagem
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem


class InMemoryPlanejamentoRepository:
    """Armazena planejamentos semanais em memória por (empresa_id, conta_ig_id)."""

    def __init__(self) -> None:
        self._itens: dict[UUID, PlanejamentoSemanal] = {}

    async def salvar(self, plano: PlanejamentoSemanal) -> PlanejamentoSemanal:
        self._itens[plano.id] = plano
        return plano

    async def buscar_por_id(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        plano_id: UUID,
    ) -> PlanejamentoSemanal | None:
        plano = self._itens.get(plano_id)
        if plano is None or plano.empresa_id != empresa_id or plano.conta_ig_id != conta_ig_id:
            return None
        return plano

    async def listar_por_conta(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
    ) -> list[PlanejamentoSemanal]:
        itens = [
            p
            for p in self._itens.values()
            if p.empresa_id == empresa_id and p.conta_ig_id == conta_ig_id
        ]
        return sorted(itens, key=lambda p: p.semana_inicio, reverse=True)

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, plano_id: UUID) -> bool:
        plano = await self.buscar_por_id(empresa_id, conta_ig_id, plano_id)
        if plano is None:
            return False
        self._itens.pop(plano_id, None)
        return True


class InMemoryPostagemRepository:
    """Armazena postagens em memória com busca por conta e fila agendada."""

    def __init__(self) -> None:
        self._itens: dict[UUID, Postagem] = {}

    async def salvar(self, postagem: Postagem) -> Postagem:
        self._itens[postagem.id] = postagem
        return postagem

    async def buscar_por_id(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        postagem_id: UUID,
    ) -> Postagem | None:
        post = self._itens.get(postagem_id)
        if post is None or post.empresa_id != empresa_id or post.conta_ig_id != conta_ig_id:
            return None
        return post

    async def listar_por_conta(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        status: StatusPostagem | None = None,
    ) -> list[Postagem]:
        itens = [
            p
            for p in self._itens.values()
            if p.empresa_id == empresa_id
            and p.conta_ig_id == conta_ig_id
            and (status is None or p.status == status)
        ]
        return sorted(itens, key=lambda p: p.criado_em, reverse=True)

    async def listar_agendadas_pendentes(self, ate_momento: datetime) -> list[Postagem]:
        return sorted(
            [
                p
                for p in self._itens.values()
                if p.status == StatusPostagem.AGENDADO
                and p.agendado_para is not None
                and p.agendado_para <= ate_momento
            ],
            key=lambda p: p.agendado_para or ate_momento,
        )

    async def listar_publicando_travadas(self, atualizado_ate: datetime) -> list[Postagem]:
        return sorted(
            [
                p
                for p in self._itens.values()
                if p.status == StatusPostagem.PUBLICANDO
                and p.atualizado_em <= atualizado_ate
            ],
            key=lambda p: p.atualizado_em,
        )

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID) -> bool:
        post = await self.buscar_por_id(empresa_id, conta_ig_id, postagem_id)
        if post is None:
            return False
        self._itens.pop(postagem_id, None)
        return True


class InMemoryCustoRepository:
    """Armazena registros de custo OpenRouter em memória com soma mensal."""

    def __init__(self) -> None:
        self._itens: list[RegistroCustoIA] = []

    async def registrar(self, registro: RegistroCustoIA) -> RegistroCustoIA:
        self._itens.append(registro)
        return registro

    async def somar_mes_empresa(self, empresa_id: UUID, ano: int, mes: int) -> Decimal:
        total = sum(
            (
                r.custo_usd
                for r in self._itens
                if r.empresa_id == empresa_id
                and r.criado_em.year == ano
                and r.criado_em.month == mes
            ),
            Decimal("0"),
        )
        return total

    async def somar_mes_por_conta(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        ano: int,
        mes: int,
    ) -> Decimal:
        total = sum(
            (
                r.custo_usd
                for r in self._itens
                if r.empresa_id == empresa_id
                and r.conta_ig_id == conta_ig_id
                and r.criado_em.year == ano
                and r.criado_em.month == mes
            ),
            Decimal("0"),
        )
        return total
