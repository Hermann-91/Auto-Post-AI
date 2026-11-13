"""Testes unitários de JwtTokenService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.seguranca.token_jwt import JwtTokenService
from app.dominio.excecoes import ErroCredenciaisInvalidas
from app.dominio.objetos_valor.enums_tenant import PapelUsuario


def test_emitir_e_decodificar_access_token() -> None:
    svc = JwtTokenService(chave_secreta="segredo-super-seguro-32-caracteres-ok")
    uid, eid = uuid4(), uuid4()

    token = svc.emitir_access_token(usuario_id=uid, empresa_id=eid, papel=PapelUsuario.ADMIN)
    payload = svc.decodificar_access_token(token)

    assert payload.usuario_id == uid
    assert payload.empresa_id == eid
    assert payload.papel == PapelUsuario.ADMIN


def test_rejeitar_token_assinado_com_outra_chave_ou_expirado() -> None:
    svc = JwtTokenService(chave_secreta="chave-a-32-caracteres-para-teste-ok")
    outro = JwtTokenService(chave_secreta="chave-b-32-caracteres-para-teste-ok")
    token_outro = outro.emitir_access_token(uuid4(), uuid4(), PapelUsuario.EDITOR)

    with pytest.raises(ErroCredenciaisInvalidas):
        svc.decodificar_access_token(token_outro)

    expirado = jwt.encode(
        {
            "sub": str(uuid4()),
            "empresa_id": str(uuid4()),
            "papel": "ADMIN",
            "type": "access",
            "iss": "robo-auto-inst",
            "aud": "robo-auto-inst-api",
            "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
        },
        "chave-a-32-caracteres-para-teste-ok",
        algorithm="HS256",
    )
    with pytest.raises(ErroCredenciaisInvalidas):
        svc.decodificar_access_token(expirado)


def test_refresh_token_opaco_e_hash_deterministico() -> None:
    svc = JwtTokenService(chave_secreta="chave-a-32-caracteres-para-teste-ok")
    t1 = svc.gerar_refresh_token_opaco()
    t2 = svc.gerar_refresh_token_opaco()

    assert t1 != t2
    assert len(svc.hash_token(t1)) == 64
    assert svc.hash_token(t1) == svc.hash_token(t1)
