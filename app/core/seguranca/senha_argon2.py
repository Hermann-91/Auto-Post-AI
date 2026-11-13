"""Hashing Argon2id assíncrono com proteção contra timing attack."""

from __future__ import annotations

import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class Argon2idHasher:
    """Adaptador de hashing de senhas usando parâmetros recomendados pela OWASP."""

    def __init__(
        self,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
    ) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=32,
            salt_len=16,
        )
        # Hash fictício gerado no boot para manter tempo constante quando e-mail não existe
        self._dummy_hash = self._hasher.hash("dummy-protecao-timing-attack")

    async def gerar_hash(self, senha_plana: str) -> str:
        """Gera hash Argon2id em thread separada para não bloquear o event loop."""
        return await asyncio.to_thread(self._hasher.hash, senha_plana)

    async def verificar(self, senha_plana: str, senha_hash: str) -> bool:
        """Verifica se a senha corresponde ao hash armazenado."""

        def _checar() -> bool:
            try:
                return self._hasher.verify(senha_hash, senha_plana)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                return False

        return await asyncio.to_thread(_checar)

    async def verificar_dummy(self, senha_plana: str) -> None:
        """Executa verificação Argon2id descartável para mitigar enumeração de e-mails."""
        await self.verificar(senha_plana, self._dummy_hash)
