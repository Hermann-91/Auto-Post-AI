"""Provedores FastAPI (Depends) para os casos de uso de IA, RAG e Planejamento."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.api.dependencias.container_ia import ContainerIA
from app.aplicacao.ia import (
    CriarConteudoUseCase,
    GeradorVisualHibrido,
    PlanejamentoSemanalUseCase,
    ServicoCuradoriaVisualUseCase,
    ServicoOrcamentoUseCase,
    ServicoPromptsRagUseCase,
)
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.infra.midia.processador_imagem import ProcessadorImagem


def obter_container_ia(request: Request) -> ContainerIA:
    """Recupera o ContainerIA anexado ao estado da aplicação."""
    return cast(ContainerIA, request.app.state.ia_container)


def obter_orcamento_uc(
    c: Annotated[ContainerIA, Depends(obter_container_ia)],
) -> ServicoOrcamentoUseCase:
    return ServicoOrcamentoUseCase(
        c.empresa_repo, c.custo_repo, c.config.openrouter_modelo_texto_fallback
    )


def obter_prompts_rag_uc(
    c: Annotated[ContainerIA, Depends(obter_container_ia)],
) -> ServicoPromptsRagUseCase:
    return ServicoPromptsRagUseCase(c.conta_repo, c.config_ia_repo, c.rag_repo)


def obter_curadoria_uc(
    c: Annotated[ContainerIA, Depends(obter_container_ia)],
    orcamento: Annotated[ServicoOrcamentoUseCase, Depends(obter_orcamento_uc)],
    prompts_rag: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> ServicoCuradoriaVisualUseCase:
    return ServicoCuradoriaVisualUseCase(
        c.midia_repo, c.storage, c.cliente_visao, orcamento, prompts_rag,
        ProcessadorImagem.compactar_entrada, c.config.openrouter_modelo_visao_padrao,
    )


def obter_criar_conteudo_uc(
    c: Annotated[ContainerIA, Depends(obter_container_ia)],
    orcamento: Annotated[ServicoOrcamentoUseCase, Depends(obter_orcamento_uc)],
    prompts_rag: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
) -> CriarConteudoUseCase:
    cota = CotaMidia(max_itens=c.config.cota_max_itens, max_bytes=c.config.cota_max_bytes)
    visual = GeradorVisualHibrido(
        c.midia_repo, c.storage, c.cliente_ia, orcamento,
        c.pipeline_midia, ProcessadorImagem.compactar_entrada, cota,
    )
    return CriarConteudoUseCase(
        c.config_ia_repo, c.midia_repo, c.post_repo, c.cliente_ia,
        orcamento, prompts_rag, visual, cota,
    )


def obter_planejamento_uc(
    c: Annotated[ContainerIA, Depends(obter_container_ia)],
    orcamento: Annotated[ServicoOrcamentoUseCase, Depends(obter_orcamento_uc)],
    prompts_rag: Annotated[ServicoPromptsRagUseCase, Depends(obter_prompts_rag_uc)],
    criador: Annotated[CriarConteudoUseCase, Depends(obter_criar_conteudo_uc)],
) -> PlanejamentoSemanalUseCase:
    return PlanejamentoSemanalUseCase(
        c.config_ia_repo, c.midia_repo, c.plano_repo, c.cliente_ia,
        c.tendencias, orcamento, prompts_rag, criador,
    )
