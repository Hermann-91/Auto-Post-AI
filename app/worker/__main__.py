"""Ponto de entrada CLI do Worker (`python -m app.worker`)."""

from __future__ import annotations

import asyncio

from app.worker.agendador import rodar_worker

if __name__ == "__main__":
    asyncio.run(rodar_worker())
