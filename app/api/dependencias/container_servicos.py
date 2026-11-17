"""Container de dependências e provedores FastAPI para Biblioteca e Serviços Web."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencias.container_ia import ContainerIA
from app.api.dependencias.provedores_ia import obter_container_ia
from app.aplicacao.biblioteca import (
    ServicoExclusaoMidiaPostUseCase,
    ServicoLimpezaPosPostagemUseCase,
    ServicoUploadCotaUseCase,
)
from app.core.config import Configuracoes
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.infra.midia.processador_imagem import ProcessadorImagem


@dataclass(slots=True)
class ContainerServicos:
    """Agrupa dependências de serviços da biblioteca e painel web."""

    config: Configuracoes
    cota_padrao: CotaMidia


def construir_container_servicos(config: Configuracoes) -> ContainerServicos:
    """Instancia configurações de serviços de biblioteca e mídia."""
    return ContainerServicos(
        config=config,
        cota_padrao=CotaMidia(
            max_itens=config.cota_max_itens,
            max_bytes=config.cota_max_bytes,
        ),
    )


def obter_container_servicos(request: Request) -> ContainerServicos:
    """Recupera o ContainerServicos anexado ao estado da aplicação."""
    return cast(ContainerServicos, request.app.state.servicos_container)


def obter_upload_cota_uc(
    ia: Annotated[ContainerIA, Depends(obter_container_ia)],
    srv: Annotated[ContainerServicos, Depends(obter_container_servicos)],
) -> ServicoUploadCotaUseCase:
    """Monta caso de uso de upload/listagem/curtida com compactação na entrada."""
    return ServicoUploadCotaUseCase(
        midia_repo=ia.midia_repo,
        storage=ia.storage,
        cota=srv.cota_padrao,
        compactador=ProcessadorImagem.compactar_entrada,
        conta_repo=ia.conta_repo,
    )


def obter_limpeza_uc(
    ia: Annotated[ContainerIA, Depends(obter_container_ia)],
) -> ServicoLimpezaPosPostagemUseCase:
    """Monta caso de uso de limpeza pós-postagem preservando favoritas."""
    return ServicoLimpezaPosPostagemUseCase(
        midia_repo=ia.midia_repo,
        post_repo=ia.post_repo,
        storage=ia.storage,
    )


def obter_exclusao_uc(
    ia: Annotated[ContainerIA, Depends(obter_container_ia)],
) -> ServicoExclusaoMidiaPostUseCase:
    """Monta caso de uso para exclusão de cards da Agenda e mídias da Biblioteca."""
    return ServicoExclusaoMidiaPostUseCase(
        conta_repo=ia.conta_repo,
        midia_repo=ia.midia_repo,
        post_repo=ia.post_repo,
        storage=ia.storage,
    )
