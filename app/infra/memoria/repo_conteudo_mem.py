"""Repositórios em memória para contas IG, ConfigIA, RAG e Biblioteca de Mídia."""

from __future__ import annotations

from uuid import UUID

from app.dominio.entidades.ia_rag import ConfigIAConta, FonteRAG
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.objetos_valor.enums_conteudo import PastaMidia


class InMemoryContaIGRepository:
    """Armazena contas Instagram em memória isoladas por empresa_id."""

    def __init__(self) -> None:
        self._itens: dict[UUID, ContaInstagram] = {}

    async def salvar(self, conta: ContaInstagram) -> ContaInstagram:
        self._itens[conta.id] = conta
        return conta

    async def buscar_por_id(self, empresa_id: UUID, conta_ig_id: UUID) -> ContaInstagram | None:
        conta = self._itens.get(conta_ig_id)
        if conta is None or conta.empresa_id != empresa_id:
            return None
        return conta

    async def listar_por_empresa(self, empresa_id: UUID) -> list[ContaInstagram]:
        return [c for c in self._itens.values() if c.empresa_id == empresa_id]


class InMemoryConfigIARepository:
    """Armazena configurações de persona/modelos em memória por (empresa_id, conta_ig_id)."""

    def __init__(self) -> None:
        self._itens: dict[tuple[UUID, UUID], ConfigIAConta] = {}

    async def obter_ou_padrao(self, empresa_id: UUID, conta_ig_id: UUID) -> ConfigIAConta:
        existente = self._itens.get((empresa_id, conta_ig_id))
        if existente is not None:
            return existente
        return ConfigIAConta(empresa_id=empresa_id, conta_ig_id=conta_ig_id)

    async def salvar(self, config: ConfigIAConta) -> ConfigIAConta:
        self._itens[(config.empresa_id, config.conta_ig_id)] = config
        return config


class InMemoryRagRepository:
    """Armazena fontes RAG em memória isoladas por (empresa_id, conta_ig_id)."""

    def __init__(self) -> None:
        self._itens: dict[UUID, FonteRAG] = {}

    async def salvar(self, fonte: FonteRAG) -> FonteRAG:
        self._itens[fonte.id] = fonte
        return fonte

    async def listar_por_conta(self, empresa_id: UUID, conta_ig_id: UUID) -> list[FonteRAG]:
        fontes = [
            f
            for f in self._itens.values()
            if f.empresa_id == empresa_id and f.conta_ig_id == conta_ig_id
        ]
        return sorted(fontes, key=lambda f: f.criado_em, reverse=True)

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, fonte_id: UUID) -> bool:
        fonte = self._itens.get(fonte_id)
        if fonte is None or fonte.empresa_id != empresa_id or fonte.conta_ig_id != conta_ig_id:
            return False
        del self._itens[fonte_id]
        return True


class InMemoryMidiaRepository:
    """Armazena metadados da biblioteca de mídia em memória com cálculo de cota."""

    def __init__(self) -> None:
        self._itens: dict[UUID, MidiaBiblioteca] = {}

    async def salvar(self, midia: MidiaBiblioteca) -> MidiaBiblioteca:
        self._itens[midia.id] = midia
        return midia

    async def buscar_por_id(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        midia_id: UUID,
    ) -> MidiaBiblioteca | None:
        midia = self._itens.get(midia_id)
        if midia is None or midia.empresa_id != empresa_id or midia.conta_ig_id != conta_ig_id:
            return None
        return midia

    async def listar_por_conta(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        pasta: PastaMidia | None = None,
    ) -> list[MidiaBiblioteca]:
        itens = [
            m
            for m in self._itens.values()
            if m.empresa_id == empresa_id
            and m.conta_ig_id == conta_ig_id
            and (pasta is None or m.pasta == pasta)
        ]
        return sorted(itens, key=lambda m: m.criado_em, reverse=True)

    async def calcular_uso_cota(self, empresa_id: UUID, conta_ig_id: UUID) -> tuple[int, int]:
        itens = await self.listar_por_conta(empresa_id, conta_ig_id)
        return len(itens), sum(m.tamanho_bytes for m in itens)

    async def remover(self, empresa_id: UUID, conta_ig_id: UUID, midia_id: UUID) -> None:
        existente = await self.buscar_por_id(empresa_id, conta_ig_id, midia_id)
        if existente is not None:
            self._itens.pop(midia_id, None)
