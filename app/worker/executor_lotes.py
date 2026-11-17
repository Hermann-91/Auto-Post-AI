"""Executor de lotes do Worker para publicações agendadas e renovação de tokens."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.aplicacao.publicacao.dtos import (
    ResultadoLoteWorkerDTO,
    ResultadoPublicacaoDTO,
    ResultadoRenovacaoTokensDTO,
)
from app.aplicacao.publicacao.resiliencia_publicacao import recuperar_postagem_travada
from app.aplicacao.publicacao.servico_agendamento import (
    LockPublicacaoPort,
    ServicoAgendamentoUseCase,
)
from app.aplicacao.publicacao.servico_oauth_meta import ServicoOAuthMetaUseCase
from app.dominio.entidades.publicacao import Postagem
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroDominio
from app.dominio.portas.repositorios_conteudo import PostagemRepositoryPort
from app.dominio.portas.repositorios_tenant import ContaIGRepositoryPort

logger = logging.getLogger(__name__)


class ExecutorLotesWorker:
    """Executa ciclos de publicação agendada e refresh preventivo de tokens Meta."""

    def __init__(
        self,
        post_repo: PostagemRepositoryPort,
        conta_repo: ContaIGRepositoryPort,
        agendamento_uc: ServicoAgendamentoUseCase,
        oauth_meta_uc: ServicoOAuthMetaUseCase,
        lock_distribuido: LockPublicacaoPort,
        dias_antes_renovar: int = 10,
        concorrencia_max: int = 3,
        lock_ttl_segundos: int = 300,
        max_tentativas_publicacao: int = 3,
    ) -> None:
        self._post_repo = post_repo
        self._conta_repo = conta_repo
        self._agendamento = agendamento_uc
        self._oauth = oauth_meta_uc
        self._lock = lock_distribuido
        self._dias_antes = dias_antes_renovar
        self._concorrencia = max(1, concorrencia_max)
        self._lock_ttl = lock_ttl_segundos
        self._max_tentativas = max(1, max_tentativas_publicacao)

    async def _recuperar_postagens_travadas(self, referencia: datetime) -> int:
        limite = referencia - timedelta(seconds=self._lock_ttl)
        travadas = await self._post_repo.listar_publicando_travadas(limite)
        recuperadas = 0
        ttl_rec = min(30, max(1, self._lock_ttl))
        for post in travadas:
            chave = f"post:{post.id}"
            token_lock = await self._lock.adquirir(chave, ttl_rec)
            if token_lock is None:
                continue
            try:
                if await recuperar_postagem_travada(
                    self._post_repo,
                    post.empresa_id,
                    post.conta_ig_id,
                    post.id,
                    limite,
                    referencia,
                    self._max_tentativas,
                ):
                    recuperadas += 1
            finally:
                await self._lock.liberar(chave, token_lock)
        return recuperadas

    async def executar_ciclo_publicacoes(
        self,
        agora: datetime | None = None,
    ) -> ResultadoLoteWorkerDTO:
        """Processa todas as postagens AGENDADO vencidas com concorrência controlada."""
        referencia = agora or datetime.now(UTC)
        recuperadas = await self._recuperar_postagens_travadas(referencia)
        pendentes = await self._post_repo.listar_agendadas_pendentes(referencia)
        if not pendentes:
            return ResultadoLoteWorkerDTO(recuperadas_travadas=recuperadas)

        semaforo = asyncio.Semaphore(self._concorrencia)

        async def _processar(post: Postagem) -> ResultadoPublicacaoDTO:
            async with semaforo:
                return await self._agendamento.publicar_postagem(
                    post.empresa_id, post.conta_ig_id, post.id
                )

        resultados = await asyncio.gather(*(_processar(p) for p in pendentes))
        publicadas = sum(1 for r in resultados if r.publicada)
        reagendadas = sum(1 for r in resultados if r.reagendada)
        ignoradas = sum(
            1
            for r in resultados
            if not r.publicada and not r.reagendada and "outro worker" in r.motivo
        )
        falhas = len(resultados) - publicadas - reagendadas - ignoradas
        return ResultadoLoteWorkerDTO(
            pendentes_encontradas=len(pendentes),
            publicadas=publicadas,
            reagendadas=reagendadas,
            falhas=falhas,
            ignoradas_por_lock=ignoradas,
            recuperadas_travadas=recuperadas,
        )

    async def _renovar_conta(self, conta: ContaInstagram) -> bool:
        chave = f"meta_refresh:{conta.id}"
        token_lock = await self._lock.adquirir(chave, self._lock_ttl)
        if token_lock is None:
            return False
        try:
            await self._oauth.renovar_token_conta(conta.empresa_id, conta.id)
            return True
        except ErroDominio as exc:
            logger.warning("Falha ao renovar token da conta %s: %s", conta.id, exc)
            return False
        except Exception:
            logger.exception("Erro inesperado ao renovar token da conta %s", conta.id)
            return False
        finally:
            await self._lock.liberar(chave, token_lock)

    async def executar_ciclo_renovacao_tokens(
        self,
        agora: datetime | None = None,
    ) -> ResultadoRenovacaoTokensDTO:
        """Renova tokens Long-Lived ativos dentro da janela de expiração configurada."""
        referencia = agora or datetime.now(UTC)
        limite = referencia + timedelta(days=self._dias_antes)
        contas = await self._conta_repo.listar_para_renovacao_token(limite)
        if not contas:
            return ResultadoRenovacaoTokensDTO()

        renovadas = 0
        falhas = 0
        for conta in contas:
            if await self._renovar_conta(conta):
                renovadas += 1
            else:
                falhas += 1
        return ResultadoRenovacaoTokensDTO(
            elegiveis=len(contas),
            renovadas=renovadas,
            falhas=falhas,
        )
