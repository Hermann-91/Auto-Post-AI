"""Casos de uso para exclusão real de postagens da Agenda e mídias da Biblioteca."""

from __future__ import annotations

import logging
from uuid import UUID

from app.aplicacao.biblioteca.dtos import (
    ResultadoExclusaoMidiaDTO,
    ResultadoExclusaoPostagemDTO,
)
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import (
    MidiaRepositoryPort,
    PostagemRepositoryPort,
)
from app.dominio.portas.repositorios_tenant import ContaIGRepositoryPort

logger = logging.getLogger(__name__)

_STATUS_ATIVOS_AGENDA: frozenset[StatusPostagem] = frozenset(
    {StatusPostagem.RASCUNHO, StatusPostagem.AGENDADO, StatusPostagem.PUBLICANDO}
)


class ServicoExclusaoMidiaPostUseCase:
    """Remove cards da Agenda com suas imagens exclusivas e exclui mídias da Biblioteca."""

    def __init__(
        self,
        conta_repo: ContaIGRepositoryPort,
        midia_repo: MidiaRepositoryPort,
        post_repo: PostagemRepositoryPort,
        storage: StorageMidiaPort,
    ) -> None:
        self._conta_repo = conta_repo
        self._midia_repo = midia_repo
        self._post_repo = post_repo
        self._storage = storage

    async def _exigir_conta(self, empresa_id: UUID, conta_ig_id: UUID) -> None:
        conta = await self._conta_repo.buscar_por_id(empresa_id, conta_ig_id)
        if conta is None:
            raise ErroValidacaoDominio("Conta Instagram não encontrada para esta empresa.")

    async def excluir_postagem_agenda(
        self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID
    ) -> ResultadoExclusaoPostagemDTO:
        """Exclui o card da Agenda e remove imagens exclusivas (não favoritas) do storage/DB."""
        await self._exigir_conta(empresa_id, conta_ig_id)
        post = await self._post_repo.buscar_por_id(empresa_id, conta_ig_id, postagem_id)
        if post is None:
            raise ErroValidacaoDominio("Postagem não encontrada para esta conta.")
        if post.status == StatusPostagem.PUBLICANDO:
            raise ErroValidacaoDominio("Não é possível excluir uma postagem em publicação ativa.")

        await self._post_repo.remover(empresa_id, conta_ig_id, postagem_id)
        restantes = await self._post_repo.listar_por_conta(empresa_id, conta_ig_id)
        chaves_em_uso = {
            ch
            for outro in restantes
            if outro.status != StatusPostagem.CANCELADO
            for ch in outro.midias_chaves
        }
        midias_conta = await self._midia_repo.listar_por_conta(empresa_id, conta_ig_id)
        mapa_midias = {m.chave_storage: m for m in midias_conta}

        chaves_removidas: list[str] = []
        preservadas = 0
        for chave in dict.fromkeys(post.midias_chaves):
            midia = mapa_midias.get(chave)
            if midia is None:
                continue
            if chave in chaves_em_uso or midia.curtida_favorita:
                preservadas += 1
                continue
            try:
                await self._storage.remover_objeto(midia.chave_storage)
                await self._midia_repo.remover(empresa_id, conta_ig_id, midia.id)
                chaves_removidas.append(chave)
            except Exception:
                logger.exception("Falha ao apagar mídia '%s' da postagem %s", midia.id, postagem_id)
                preservadas += 1

        return ResultadoExclusaoPostagemDTO(
            postagem_id=postagem_id,
            midias_removidas_qtd=len(chaves_removidas),
            chaves_removidas=chaves_removidas,
            midias_preservadas_qtd=preservadas,
        )

    async def excluir_midia_biblioteca(
        self, empresa_id: UUID, conta_ig_id: UUID, midia_id: UUID
    ) -> ResultadoExclusaoMidiaDTO:
        """Exclui uma mídia da Biblioteca caso não esteja vinculada a post ativo na Agenda."""
        await self._exigir_conta(empresa_id, conta_ig_id)
        midia = await self._midia_repo.buscar_por_id(empresa_id, conta_ig_id, midia_id)
        if midia is None:
            raise ErroValidacaoDominio("Mídia não encontrada para esta conta.")

        posts = await self._post_repo.listar_por_conta(empresa_id, conta_ig_id)
        em_uso = any(
            p.status in _STATUS_ATIVOS_AGENDA and midia.chave_storage in p.midias_chaves
            for p in posts
        )
        if em_uso:
            raise ErroValidacaoDominio(
                "Mídia vinculada a um card ativo na Agenda. "
                "Exclua ou troque a foto na Agenda primeiro."
            )

        await self._storage.remover_objeto(midia.chave_storage)
        await self._midia_repo.remover(empresa_id, conta_ig_id, midia.id)
        return ResultadoExclusaoMidiaDTO(
            midia_id=midia.id,
            chave_storage=midia.chave_storage,
            bytes_liberados=midia.tamanho_bytes,
        )
