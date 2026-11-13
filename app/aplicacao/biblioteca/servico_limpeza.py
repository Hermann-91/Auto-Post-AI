"""Caso de uso para limpeza de mídias pós-postagem protegendo favoritas."""

from __future__ import annotations

import logging
from uuid import UUID

from app.aplicacao.biblioteca.dtos import ResultadoLimpezaDTO
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import (
    MidiaRepositoryPort,
    PostagemRepositoryPort,
)

logger = logging.getLogger(__name__)

STATUS_POST_PROTEGIDOS: frozenset[StatusPostagem] = frozenset(
    {
        StatusPostagem.RASCUNHO,
        StatusPostagem.AGENDADO,
        StatusPostagem.PUBLICANDO,
        StatusPostagem.FALHA,
    }
)


class ServicoLimpezaPosPostagemUseCase:
    """Remove mídias já publicadas do storage/DB mantendo favoritas e filas ativas."""

    def __init__(
        self,
        midia_repo: MidiaRepositoryPort,
        post_repo: PostagemRepositoryPort,
        storage: StorageMidiaPort,
    ) -> None:
        self._midia_repo = midia_repo
        self._post_repo = post_repo
        self._storage = storage

    async def executar(self, empresa_id: UUID, conta_ig_id: UUID) -> ResultadoLimpezaDTO:
        """Executa limpeza segura para a conta informada."""
        midias = await self._midia_repo.listar_por_conta(empresa_id, conta_ig_id)
        postagens = await self._post_repo.listar_por_conta(empresa_id, conta_ig_id)

        chaves_protegidas: set[str] = set()
        chaves_publicadas: set[str] = set()
        for post in postagens:
            if post.status in STATUS_POST_PROTEGIDOS:
                chaves_protegidas.update(post.midias_chaves)
            elif post.status == StatusPostagem.PUBLICADO:
                chaves_publicadas.update(post.midias_chaves)

        chaves_removidas: list[str] = []
        bytes_liberados = 0
        falhas = 0

        for midia in midias:
            if midia.chave_storage not in chaves_publicadas:
                continue
            vinculada_ativa = midia.chave_storage in chaves_protegidas
            if not midia.pode_ser_limpa(vinculada_a_post_ativo=vinculada_ativa):
                continue

            try:
                await self._storage.remover_objeto(midia.chave_storage)
                await self._midia_repo.remover(empresa_id, conta_ig_id, midia.id)
            except Exception:
                logger.exception("Falha ao remover mídia pós-postagem: %s", midia.id)
                falhas += 1
                continue

            chaves_removidas.append(midia.chave_storage)
            bytes_liberados += midia.tamanho_bytes

        return ResultadoLimpezaDTO(
            removidas_qtd=len(chaves_removidas),
            bytes_liberados=bytes_liberados,
            chaves_removidas=chaves_removidas,
            falhas=falhas,
        )
