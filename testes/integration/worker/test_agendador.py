"""Testes de integração do loop AgendadorWorker e composição do Worker."""

from __future__ import annotations

import asyncio

from app.core.config import Configuracoes
from app.worker.agendador import AgendadorWorker, construir_executor_worker


class _FakeExecutor:
    def __init__(self) -> None:
        self.ciclos_pub = 0
        self.ciclos_tok = 0

    async def executar_ciclo_publicacoes(self) -> object:
        self.ciclos_pub += 1

        class _R:
            pendentes_encontradas = 0
            publicadas = 0
            reagendadas = 0
            falhas = 0

        return _R()

    async def executar_ciclo_renovacao_tokens(self) -> object:
        self.ciclos_tok += 1

        class _T:
            elegiveis = 0
            renovadas = 0
            falhas = 0

        return _T()


async def test_agendador_executa_ciclos_e_constroi_worker() -> None:
    fake_exec = _FakeExecutor()
    agendador = AgendadorWorker(
        executor=fake_exec,  # type: ignore[arg-type]
        intervalo_poll_segundos=0.01,
        intervalo_renovacao_segundos=3600.0,
    )
    ciclos = await agendador.rodar(max_ciclos=2)
    assert ciclos == 2
    assert fake_exec.ciclos_pub == 2
    assert fake_exec.ciclos_tok == 1

    parada = asyncio.Event()
    parada.set()
    assert await agendador.rodar(evento_parada=parada) == 0

    cfg = Configuracoes(app_env="test", argon2_time_cost=1, argon2_memory_cost_kib=8192)
    executor_real, fechar = construir_executor_worker(cfg)
    assert executor_real is not None
    await fechar()
