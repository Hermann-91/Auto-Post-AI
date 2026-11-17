"""Caso de uso para orquestração assíncrona de jobs de criação, plano e recriação."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.aplicacao.ia.criar_conteudo import CriarConteudoUseCase
from app.aplicacao.ia.dtos import CriarConteudoCmd, ProporPlanejamentoCmd
from app.aplicacao.ia.edicao_orcamento_semanal import EdicaoOrcamentoSemanalUseCase
from app.aplicacao.ia.jobs_store import (
    JobIAStore,
    serializar_conteudo,
    serializar_execucao_plano,
    serializar_plano,
    serializar_postagem,
)
from app.aplicacao.ia.planejamento_semanal import PlanejamentoSemanalUseCase
from app.aplicacao.ia.recriar_postagem_contexto import RecriarPostagemContextoUseCase
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.job_ia import JobIA, TipoJobIA
from app.dominio.excecoes import ErroDominio
from app.dominio.objetos_valor.enums_conteudo import StatusPlanejamento

logger = logging.getLogger(__name__)


class ServicoJobsIAUseCase:
    """Agenda e monitora jobs assíncronos isolados por (empresa_id, conta_ig_id)."""

    def __init__(
        self,
        store: JobIAStore,
        prompts_rag: ServicoPromptsRagUseCase,
        criar_conteudo: CriarConteudoUseCase,
        planejamento: PlanejamentoSemanalUseCase,
        edicao_orcamento: EdicaoOrcamentoSemanalUseCase,
        recriar_post: RecriarPostagemContextoUseCase,
    ) -> None:
        self._store = store
        self._prompts_rag = prompts_rag
        self._criar = criar_conteudo
        self._planejamento = planejamento
        self._edicao = edicao_orcamento
        self._recriar = recriar_post

    async def criar_e_agendar(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        tipo_job: TipoJobIA,
        cmd_ou_dados: CriarConteudoCmd | ProporPlanejamentoCmd | dict[str, Any],
        chave_idempotencia: str = "",
    ) -> JobIA:
        """Valida conta, evita duplicata ativa por idempotência e inicia task em background."""
        await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        existente = await self._store.buscar_ativo_idempotente(
            empresa_id, conta_ig_id, tipo_job, chave_idempotencia
        )
        if existente is not None:
            return existente

        total = 1
        if tipo_job == TipoJobIA.EXECUTAR_PLANO and isinstance(cmd_ou_dados, dict):
            plano = await self._planejamento.obter_plano(
                empresa_id, conta_ig_id, UUID(str(cmd_ou_dados["plano_id"]))
            )
            total = max(1, len(plano.itens_grade))
        elif tipo_job == TipoJobIA.CRIAR_CONTEUDO and isinstance(cmd_ou_dados, CriarConteudoCmd):
            total = 2 if cmd_ou_dados.gerar_imagem_ia or cmd_ou_dados.editar_midia_id else 1

        job = JobIA(
            empresa_id=empresa_id,
            conta_ig_id=conta_ig_id,
            tipo_job=tipo_job,
            progresso_total=total,
            chave_idempotencia=chave_idempotencia,
        )
        await self._store.salvar(job)
        task = asyncio.create_task(self._executar_seguro(job, cmd_ou_dados))
        self._store.registrar_task(task)
        return job

    async def obter_job(self, empresa_id: UUID, job_id: UUID) -> JobIA | None:
        return await self._store.buscar_por_id(empresa_id, job_id)

    async def listar_jobs_conta(
        self, empresa_id: UUID, conta_ig_id: UUID, apenas_ativos: bool = False
    ) -> list[JobIA]:
        await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        return await self._store.listar_por_conta(empresa_id, conta_ig_id, apenas_ativos)

    async def _executar_seguro(
        self,
        job: JobIA,
        cmd_ou_dados: CriarConteudoCmd | ProporPlanejamentoCmd | dict[str, Any],
    ) -> None:
        try:
            resultado = await self._despachar(job, cmd_ou_dados)
            job.concluir(resultado)
        except ErroDominio as exc:
            job.falhar(str(exc))
        except asyncio.CancelledError:
            job.falhar("Execução cancelada pelo servidor.")
            raise
        except Exception:
            logger.exception("Erro inesperado no job IA %s (%s).", job.id, job.tipo_job)
            job.falhar("Falha interna ao processar job de IA.")
        finally:
            await self._store.salvar(job)

    async def _despachar(
        self,
        job: JobIA,
        cmd_ou_dados: CriarConteudoCmd | ProporPlanejamentoCmd | dict[str, Any],
    ) -> dict[str, Any]:
        if job.tipo_job == TipoJobIA.CRIAR_CONTEUDO and isinstance(cmd_ou_dados, CriarConteudoCmd):
            job.iniciar("Gerando legenda e briefing...")
            await self._store.salvar(job)
            res = await self._criar.executar(cmd_ou_dados)
            if job.progresso_total > 1:
                job.avancar(1, "Finalizando arte e rascunho...")
                await self._store.salvar(job)
            return serializar_conteudo(res)

        if job.tipo_job == TipoJobIA.PROPOR_PLANO and isinstance(
            cmd_ou_dados, ProporPlanejamentoCmd
        ):
            job.iniciar("Pesquisando tendências e estruturando grade...")
            await self._store.salvar(job)
            plano = await self._planejamento.propor_semana(cmd_ou_dados)
            if cmd_ou_dados.midia_ids_anexadas:
                plano = await self._edicao.encaixar_midias_na_semana(
                    empresa_id=job.empresa_id,
                    conta_ig_id=job.conta_ig_id,
                    plano=plano,
                    midia_ids=cmd_ou_dados.midia_ids_anexadas,
                    presets_melhoria=cmd_ou_dados.presets_melhoria,
                    instrucao_melhoria=cmd_ou_dados.instrucao_melhoria,
                )
            return serializar_plano(plano)

        if job.tipo_job == TipoJobIA.EXECUTAR_PLANO and isinstance(cmd_ou_dados, dict):
            return await self._executar_plano_job(job, cmd_ou_dados)

        if job.tipo_job == TipoJobIA.RECRIAR_POSTAGEM and isinstance(cmd_ou_dados, dict):
            job.iniciar("Recriando publicação com Cultura RAG...")
            await self._store.salvar(job)
            post = await self._recriar.recriar_com_contexto(
                empresa_id=job.empresa_id,
                conta_ig_id=job.conta_ig_id,
                postagem_id=UUID(str(cmd_ou_dados["postagem_id"])),
                alvo=str(cmd_ou_dados["alvo"]),
                contexto_adicional=str(cmd_ou_dados.get("contexto_adicional") or ""),
                presets_melhoria=tuple(cmd_ou_dados.get("presets_melhoria") or ()),
                midia_base_id=(
                    UUID(str(cmd_ou_dados["midia_base_id"]))
                    if cmd_ou_dados.get("midia_base_id")
                    else None
                ),
            )
            return serializar_postagem(post)

        raise ErroDominio("Payload incompatível com o tipo de job solicitado.")

    async def _executar_plano_job(self, job: JobIA, dados: dict[str, Any]) -> dict[str, Any]:
        plano_id = UUID(str(dados["plano_id"]))
        plano = await self._planejamento.obter_plano(job.empresa_id, job.conta_ig_id, plano_id)
        job.iniciar("Validando orçamento e iniciando lote...", max(1, len(plano.itens_grade)))
        await self._store.salvar(job)
        if plano.status == StatusPlanejamento.AGUARDANDO_APROVACAO:
            await self._planejamento.aprovar_plano(job.empresa_id, job.conta_ig_id, plano_id)

        async def _progredir(atual: int, total: int, etapa: str) -> None:
            job.progresso_total = max(1, total)
            job.avancar(atual, etapa)
            await self._store.salvar(job)

        res = await self._planejamento.executar_plano(
            job.empresa_id,
            job.conta_ig_id,
            plano_id,
            auto_agendar=dados.get("auto_agendar"),
            fuso_horario=dados.get("fuso_horario"),
            ao_progredir=_progredir,
        )
        return serializar_execucao_plano(res)
