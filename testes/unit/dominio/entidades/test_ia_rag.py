"""Testes unitários das entidades de configuração IA, RAG e custo."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.dominio.entidades.ia_rag import ConfigIAConta, FonteRAG, RegistroCustoIA
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG


def test_config_ia_e_fonte_rag() -> None:
    eid, cid = uuid4(), uuid4()
    cfg = ConfigIAConta(empresa_id=eid, conta_ig_id=cid)
    fonte = FonteRAG(
        empresa_id=eid,
        conta_ig_id=cid,
        tipo=TipoFonteRAG.FAQ,
        titulo=" Horário ",
        conteudo_limpo="Atendemos das 8h às 18h.",
        chunks=["Atendemos das 8h às 18h."],
    )
    assert cfg.aplicar_logo_padrao is False
    assert fonte.titulo == "Horário"

    with pytest.raises(ErroValidacaoDominio):
        FonteRAG(
            empresa_id=eid,
            conta_ig_id=cid,
            tipo=TipoFonteRAG.TEXTO,
            titulo="",
            conteudo_limpo="x",
        )


def test_registro_custo_nao_aceita_valores_negativos() -> None:
    with pytest.raises(ErroValidacaoDominio):
        RegistroCustoIA(
            empresa_id=uuid4(),
            conta_ig_id=uuid4(),
            openrouter_gen_id="gen-1",
            modelo="deepseek/deepseek-v4-flash",
            tokens_in=10,
            tokens_out=5,
            custo_usd=Decimal("-0.01"),
        )
