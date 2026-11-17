"""Portas de repositório escopadas por (empresa_id, conta_ig_id)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.dominio.entidades.ia_rag import ConfigIAConta, FonteRAG, RegistroCustoIA
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import PlanejamentoSemanal, Postagem
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, StatusPostagem


class ConfigIARepositoryPort(Protocol):
    async def obter_ou_padrao(self, empresa_id: UUID, conta_ig_id: UUID) -> ConfigIAConta: ...
    async def salvar(self, config: ConfigIAConta) -> ConfigIAConta: ...


class RagRepositoryPort(Protocol):
    async def salvar(self, fonte: FonteRAG) -> FonteRAG: ...
    async def listar_por_conta(self, empresa_id: UUID, conta_ig_id: UUID) -> list[FonteRAG]: ...
    async def remover(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        fonte_id: UUID,
    ) -> bool: ...


class MidiaRepositoryPort(Protocol):
    async def salvar(self, midia: MidiaBiblioteca) -> MidiaBiblioteca: ...
    async def buscar_por_id(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        midia_id: UUID,
    ) -> MidiaBiblioteca | None: ...
    async def listar_por_conta(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        pasta: PastaMidia | None = None,
    ) -> list[MidiaBiblioteca]: ...
    async def calcular_uso_cota(self, empresa_id: UUID, conta_ig_id: UUID) -> tuple[int, int]: ...
    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, midia_id: UUID) -> None: ...


class PlanejamentoRepositoryPort(Protocol):
    async def salvar(self, plano: PlanejamentoSemanal) -> PlanejamentoSemanal: ...
    async def buscar_por_id(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        plano_id: UUID,
    ) -> PlanejamentoSemanal | None: ...
    async def listar_por_conta(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
    ) -> list[PlanejamentoSemanal]: ...


class PostagemRepositoryPort(Protocol):
    async def salvar(self, postagem: Postagem) -> Postagem: ...
    async def buscar_por_id(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        postagem_id: UUID,
    ) -> Postagem | None: ...
    async def listar_por_conta(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        status: StatusPostagem | None = None,
    ) -> list[Postagem]: ...
    async def listar_agendadas_pendentes(self, ate_momento: datetime) -> list[Postagem]: ...
    async def listar_publicando_travadas(self, atualizado_ate: datetime) -> list[Postagem]: ...
    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID) -> bool: ...


class CustoRepositoryPort(Protocol):
    async def registrar(self, registro: RegistroCustoIA) -> RegistroCustoIA: ...
    async def somar_mes_empresa(self, empresa_id: UUID, ano: int, mes: int) -> Decimal: ...
    async def somar_mes_por_conta(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        ano: int,
        mes: int,
    ) -> Decimal: ...
