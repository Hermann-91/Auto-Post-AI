"""Testes unitários das entidades Postagem e PlanejamentoSemanal."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.dominio.entidades.publicacao import PlanejamentoSemanal, Postagem
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import (
    StatusPlanejamento,
    StatusPostagem,
    TipoMidia,
)


def test_invariantes_carrossel_e_stories() -> None:
    eid, cid = uuid4(), uuid4()
    with pytest.raises(ErroValidacaoDominio):
        Postagem(
            empresa_id=eid,
            conta_ig_id=cid,
            tipo_midia=TipoMidia.CAROUSEL,
            midias_chaves=["1.jpg"],
        )
    with pytest.raises(ErroValidacaoDominio):
        Postagem(
            empresa_id=eid,
            conta_ig_id=cid,
            tipo_midia=TipoMidia.STORIES,
            midias_chaves=["1.jpg"],
            legenda="Stories não aceita legenda",
        )


def test_ciclo_de_vida_postagem_e_planejamento() -> None:
    post = Postagem(
        empresa_id=uuid4(),
        conta_ig_id=uuid4(),
        tipo_midia=TipoMidia.IMAGE,
        midias_chaves=["foto.jpg"],
        legenda="Post teste",
    )
    post.agendar(datetime.now(UTC) + timedelta(hours=2))
    post.iniciar_publicacao()
    post.marcar_publicado(meta_media_id="179999", meta_container_id="178888")
    assert post.status == StatusPostagem.PUBLICADO

    plano = PlanejamentoSemanal(
        empresa_id=post.empresa_id,
        conta_ig_id=post.conta_ig_id,
        semana_inicio=date.today(),
    )
    plano.enviar_para_aprovacao()
    plano.aprovar()
    plano.iniciar_execucao()
    plano.concluir()
    assert plano.status == StatusPlanejamento.CONCLUIDO
