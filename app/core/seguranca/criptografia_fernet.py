"""Criptografia simétrica autenticada (MultiFernet) para segredos no banco."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.dominio.excecoes import ErroSegurancaInterna


class FernetCipher:
    """Encapsula MultiFernet permitindo rotação de chaves sem quebra de leitura."""

    def __init__(self, chaves_fernet: list[str]) -> None:
        if not chaves_fernet:
            raise ValueError("Ao menos uma chave Fernet deve ser fornecida.")
        instancias = [Fernet(chave.encode("utf-8")) for chave in chaves_fernet]
        self._cipher = MultiFernet(instancias)

    def criptografar(self, texto_plano: str) -> str:
        """Criptografa texto sensível com a chave Fernet primária."""
        if not texto_plano:
            raise ValueError("Texto para criptografia não pode ser vazio.")
        token_bytes = self._cipher.encrypt(texto_plano.encode("utf-8"))
        return token_bytes.decode("utf-8")

    def descriptografar(self, texto_cifrado: str) -> str:
        """Descriptografa usando qualquer chave válida cadastrada no MultiFernet."""
        try:
            plano_bytes = self._cipher.decrypt(texto_cifrado.encode("utf-8"))
            return plano_bytes.decode("utf-8")
        except InvalidToken as exc:
            raise ErroSegurancaInterna("Falha ao descriptografar credencial.") from exc
