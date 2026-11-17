"""Casos de uso e DTOs de IA: orçamento, prompts/RAG, criação e planejamento."""

from app.aplicacao.ia.avaliador_visual import AvaliadorVisualCritico
from app.aplicacao.ia.criar_conteudo import CriarConteudoUseCase
from app.aplicacao.ia.diretor_arte import DiretorArteService
from app.aplicacao.ia.dtos import (
    AtualizarConfigIACmd,
    CompactadorMiniaturaPort,
    ConteudoGeradoDTO,
    CriarConteudoCmd,
    CuradoriaVisualDTO,
    DecisaoOrcamentoDTO,
    IndexarArquivoRagCmd,
    IndexarFonteRagCmd,
    IndexarUrlRagCmd,
    PipelineMidiaPort,
    ProporPlanejamentoCmd,
    ResultadoExecucaoPlanoDTO,
    ResumoOrcamentoDTO,
)
from app.aplicacao.ia.dtos_visuais import (
    QualidadeRevisaoVisual,
    ResultadoGeracaoVisual,
    SceneSpec,
    VereditoCriticoVisual,
)
from app.aplicacao.ia.edicao_orcamento_semanal import EdicaoOrcamentoSemanalUseCase
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.jobs_store import JobIAStore
from app.aplicacao.ia.planejamento_semanal import PlanejamentoSemanalUseCase
from app.aplicacao.ia.recriar_postagem_contexto import RecriarPostagemContextoUseCase
from app.aplicacao.ia.servico_curadoria import (
    CuradoriaLoteDTO,
    ServicoCuradoriaVisualUseCase,
)
from app.aplicacao.ia.servico_jobs import ServicoJobsIAUseCase
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase

__all__ = [
    "AtualizarConfigIACmd",
    "AvaliadorVisualCritico",
    "CompactadorMiniaturaPort",
    "ConteudoGeradoDTO",
    "CriarConteudoCmd",
    "CriarConteudoUseCase",
    "CuradoriaLoteDTO",
    "CuradoriaVisualDTO",
    "DecisaoOrcamentoDTO",
    "DiretorArteService",
    "EdicaoOrcamentoSemanalUseCase",
    "GeradorVisualHibrido",
    "IndexarArquivoRagCmd",
    "IndexarFonteRagCmd",
    "IndexarUrlRagCmd",
    "JobIAStore",
    "PipelineMidiaPort",
    "PlanejamentoSemanalUseCase",
    "ProporPlanejamentoCmd",
    "QualidadeRevisaoVisual",
    "RecriarPostagemContextoUseCase",
    "ResultadoExecucaoPlanoDTO",
    "ResultadoGeracaoVisual",
    "ResumoOrcamentoDTO",
    "SceneSpec",
    "ServicoCuradoriaVisualUseCase",
    "ServicoJobsIAUseCase",
    "ServicoOrcamentoUseCase",
    "ServicoPromptsRagUseCase",
    "VereditoCriticoVisual",
]
