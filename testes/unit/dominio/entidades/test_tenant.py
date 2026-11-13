"""Testes unitários das entidades de tenant e conta Instagram."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.dominio.entidades.tenant import (
    ContaInstagram,
    Empresa,
    RefreshTokenRegistro,
    Usuario,
)
from app.dominio.excecoes import ErroValidacaoDominio


def test_empresa_e_usuario_validacoes() -> None:
    emp = Empresa(nome="  Agência Sol  ", limite_mensal_usd=Decimal("25.00"))
    usr = Usuario(empresa_id=emp.id, email=" Admin@Sol.com ", senha_hash="hash")

    assert emp.nome == "Agência Sol"
    assert usr.email == "admin@sol.com"

    with pytest.raises(ErroValidacaoDominio):
        Empresa(nome="A")
    with pytest.raises(ErroValidacaoDominio):
        Usuario(empresa_id=emp.id, email="invalido", senha_hash="hash")


def test_refresh_token_validade_e_conta_instagram() -> None:
    agora = datetime.now(UTC)
    rt = RefreshTokenRegistro(
        usuario_id=uuid4(),
        empresa_id=uuid4(),
        familia_id=uuid4(),
        token_hash="abc",
        expira_em=agora + timedelta(hours=1),
    )
    assert rt.esta_valido(agora) is True
    rt.revogado = True
    assert rt.esta_valido(agora) is False

    conta = ContaInstagram(
        empresa_id=uuid4(),
        ig_user_id="17841400001",
        username=" @minhaloja ",
        access_token_enc="cifrado",
        token_expira_em=agora - timedelta(minutes=1),
    )
    assert conta.username == "minhaloja"
    assert conta.token_expirado(agora) is True
    conta.atualizar_token("novo-cifrado", agora + timedelta(days=60))
    assert conta.token_expirado(agora) is False
