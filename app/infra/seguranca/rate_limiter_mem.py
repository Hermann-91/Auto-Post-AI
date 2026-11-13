"""Rate limiter em memória com janela deslizante para dev e testes."""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict, deque
from collections.abc import Callable


class InMemoryRateLimiter:
    """Limita tentativas por chave usando janela deslizante determinística."""

    def __init__(
        self,
        max_tentativas: int = 5,
        janela_segundos: int = 900,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_tentativas = max_tentativas
        self._janela_segundos = janela_segundos
        self._relogio = relogio
        self._registros: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def verificar_e_consumir(self, chave: str) -> tuple[bool, int]:
        """Retorna (permitido, retry_after_segundos)."""
        async with self._lock:
            agora = self._relogio()
            limite_inferior = agora - self._janela_segundos
            fila = self._registros[chave]

            while fila and fila[0] <= limite_inferior:
                fila.popleft()

            if len(fila) >= self._max_tentativas:
                restante = math.ceil(self._janela_segundos - (agora - fila[0]))
                return False, max(1, restante)

            fila.append(agora)
            return True, 0
