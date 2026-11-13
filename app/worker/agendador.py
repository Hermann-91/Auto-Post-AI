"""Loop principal do processo Worker de agendamento e renovação de tokens."""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from collections.abc import Awaitable, Callable

from app.api.dependencias.container_auth import construir_container_auth
from app.api.dependencias.container_ia import construir_container_ia
from app.api.dependencias.container_meta import (
    construir_container_meta,
    criar_agendamento_uc,
    criar_oauth_meta_uc,
)
from app.core.config import Configuracoes, obter_configuracoes
from app.core.logging_config import configurar_logging
from app.worker.executor_lotes import ExecutorLotesWorker

logger = logging.getLogger(__name__)
SleepFn = Callable[[float], Awaitable[None]]


def construir_executor_worker(
    config: Configuracoes,
) -> tuple[ExecutorLotesWorker, Callable[[], Awaitable[None]]]:
    """Constrói composição completa do Worker reutilizando containers da API."""
    auth = construir_container_auth(config)
    ia = construir_container_ia(config, auth)
    meta = construir_container_meta(config, auth, ia)
    executor = ExecutorLotesWorker(
        post_repo=ia.post_repo,
        conta_repo=ia.conta_repo,
        agendamento_uc=criar_agendamento_uc(ia, meta),
        oauth_meta_uc=criar_oauth_meta_uc(ia, meta),
        lock_distribuido=meta.lock_distribuido,
        dias_antes_renovar=config.worker_renovar_token_dias_antes,
        concorrencia_max=config.worker_concorrencia_max,
        lock_ttl_segundos=config.worker_lock_ttl_segundos,
    )
    return executor, auth.fechar


class AgendadorWorker:
    """Orquestra polling de postagens e renovação periódica de tokens Meta."""

    def __init__(
        self,
        executor: ExecutorLotesWorker,
        intervalo_poll_segundos: float = 15.0,
        intervalo_renovacao_segundos: float = 3600.0,
        sleep_fn: SleepFn = asyncio.sleep,
    ) -> None:
        self._executor = executor
        self._poll = intervalo_poll_segundos
        self._intervalo_renovacao = intervalo_renovacao_segundos
        self._sleep = sleep_fn
        self._ultima_renovacao = 0.0

    async def executar_uma_iteracao(self) -> None:
        """Executa ciclo de publicações e, quando devido, renovação de tokens."""
        res_pub = await self._executor.executar_ciclo_publicacoes()
        if res_pub.pendentes_encontradas > 0:
            logger.info(
                "Worker ciclo: pendentes=%s publicadas=%s reagendadas=%s falhas=%s",
                res_pub.pendentes_encontradas,
                res_pub.publicadas,
                res_pub.reagendadas,
                res_pub.falhas,
            )
        agora_mono = time.monotonic()
        if self._ultima_renovacao == 0.0 or (
            agora_mono - self._ultima_renovacao >= self._intervalo_renovacao
        ):
            res_tok = await self._executor.executar_ciclo_renovacao_tokens()
            self._ultima_renovacao = agora_mono
            if res_tok.elegiveis > 0:
                logger.info(
                    "Worker tokens: elegiveis=%s renovadas=%s falhas=%s",
                    res_tok.elegiveis,
                    res_tok.renovadas,
                    res_tok.falhas,
                )

    async def rodar(
        self,
        evento_parada: asyncio.Event | None = None,
        max_ciclos: int | None = None,
    ) -> int:
        """Executa loop contínuo até sinal de parada ou limite opcional de ciclos."""
        parada = evento_parada or asyncio.Event()
        ciclos = 0
        while not parada.is_set():
            try:
                await self.executar_uma_iteracao()
            except Exception:
                logger.exception("Falha inesperada na iteração do Worker.")
            ciclos += 1
            if max_ciclos is not None and ciclos >= max_ciclos:
                break
            try:
                await asyncio.wait_for(parada.wait(), timeout=self._poll)
            except TimeoutError:
                continue
        return ciclos


async def rodar_worker(config: Configuracoes | None = None) -> None:
    """Inicializa recursos, registra sinais POSIX e executa Worker até shutdown."""
    configurar_logging()
    cfg = config or obter_configuracoes()
    executor, fechar = construir_executor_worker(cfg)
    parada = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, parada.set)

    agendador = AgendadorWorker(
        executor=executor,
        intervalo_poll_segundos=cfg.worker_poll_segundos,
    )
    logger.info("Worker de agendamento iniciado (poll=%ss).", cfg.worker_poll_segundos)
    try:
        await agendador.rodar(evento_parada=parada)
    finally:
        await fechar()
        logger.info("Worker encerrado com segurança.")
