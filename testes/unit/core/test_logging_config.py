"""Testes unitários do filtro e formatador JSON anti-vazamento de segredos em logs."""

from __future__ import annotations

import json
import logging
import sys

from app.core.logging_config import (
    FiltroMascaraSegredos,
    FormatadorJsonSeguro,
    mascarar_segredos,
)


def test_mascarar_segredos_redige_tokens_chaves_e_urls() -> None:
    bruto = (
        "Auth Bearer secret.jwt.tok fernet=gAAAAABl1234_xyz= "
        "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c "
        "or=sk-or-v1-998877665544332211 "
        "url=https://graph.instagram.com/me?access_token=IGQVJ12345&client_secret=meu_segredo "
        "db=postgresql+asyncpg://robo:SenhaSuperForte@db:5432/app "
        "redis=redis://:SenhaRedisSecreta@redis:6379/0"
    )
    limpo = mascarar_segredos(bruto)
    assert "secret.jwt.tok" not in limpo
    assert "gAAAAABl1234_xyz=" not in limpo
    assert "eyJhbGciOiJIUzI1NiJ9" not in limpo
    assert "sk-or-v1-998877665544332211" not in limpo
    assert "IGQVJ12345" not in limpo
    assert "meu_segredo" not in limpo
    assert "SenhaSuperForte" not in limpo
    assert "SenhaRedisSecreta" not in limpo
    assert "[REDIGIDO]" in limpo


def test_formatador_json_mascara_args_interpolados_e_excecoes() -> None:
    filtro = FiltroMascaraSegredos()
    formatador = FormatadorJsonSeguro()
    logger = logging.getLogger("teste.seguranca")

    try:
        raise RuntimeError("Falha com token Bearer tok_secreto_123 e access_token=abc999")
    except RuntimeError:
        record = logger.makeRecord(
            name="teste.seguranca",
            level=logging.ERROR,
            fn="x.py",
            lno=10,
            msg="Erro ao autenticar: %s",
            args=("client_secret=segredo_arg_456",),
            exc_info=sys.exc_info(),
        )

    assert filtro.filter(record) is True
    saida = json.loads(formatador.format(record))
    assert "segredo_arg_456" not in saida["mensagem"]
    assert "[REDIGIDO]" in saida["mensagem"]
    assert "tok_secreto_123" not in saida["excecao"]
    assert "abc999" not in saida["excecao"]
