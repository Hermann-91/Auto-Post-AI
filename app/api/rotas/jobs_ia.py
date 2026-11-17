"""Rotas HTTP para disparo e polling de jobs assíncronos de IA."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencias.provedores_ia import obter_jobs_ia_uc
from app.api.dependencias.usuario_atual import obter_usuario_atual
from app.api.schemas.jobs_ia import CriarJobIARequest, JobIAResponse
from app.aplicacao.ia import CriarConteudoCmd, ProporPlanejamentoCmd, ServicoJobsIAUseCase
from app.dominio.entidades.job_ia import JobIA, TipoJobIA
from app.dominio.portas.seguranca import PayloadAccessToken

router = APIRouter(prefix="/ia", tags=["jobs-ia"])


def _to_job_response(job: JobIA) -> JobIAResponse:
    return JobIAResponse(
        id=job.id,
        conta_ig_id=job.conta_ig_id,
        tipo_job=job.tipo_job,
        status=job.status,
        etapa_atual=job.etapa_atual,
        progresso_atual=job.progresso_atual,
        progresso_total=job.progresso_total,
        percentual=job.percentual,
        resultado_json=job.resultado_json,
        erro_detalhe=job.erro_detalhe,
        criado_em=job.criado_em,
        atualizado_em=job.atualizado_em,
    )


def _converter_cmd(
    empresa_id: UUID, payload: CriarJobIARequest
) -> CriarConteudoCmd | ProporPlanejamentoCmd | dict[str, Any]:
    if payload.tipo_job == TipoJobIA.CRIAR_CONTEUDO and payload.criar_conteudo is not None:
        c = payload.criar_conteudo
        return CriarConteudoCmd(
            empresa_id=empresa_id, conta_ig_id=payload.conta_ig_id, tipo_midia=c.tipo_midia,
            tema=c.tema, objetivo=c.objetivo, tom_extra=c.tom_extra,
            gerar_imagem_ia=c.gerar_imagem_ia, editar_midia_id=c.editar_midia_id,
            midia_base_ids=tuple(c.midia_base_ids), prompt_visual_extra=c.prompt_visual_extra,
            presets_melhoria=tuple(c.presets_melhoria), proporcao=c.proporcao,
            aplicar_logo=c.aplicar_logo, salvar_rascunho=c.salvar_rascunho,
            modelo_texto=c.modelo_texto, modelo_imagem=c.modelo_imagem,
            pilar_editorial=c.pilar_editorial, modo_serie=c.modo_serie,
            etapa_serie=c.etapa_serie, prompt_avancado=c.prompt_avancado,
            agendar_para=c.agendar_para,
        )
    if payload.tipo_job == TipoJobIA.PROPOR_PLANO and payload.propor_plano is not None:
        p = payload.propor_plano
        return ProporPlanejamentoCmd(
            empresa_id=empresa_id, conta_ig_id=payload.conta_ig_id, semana_inicio=p.semana_inicio,
            nicho=p.nicho, regiao=p.regiao, objetivo_semana=p.objetivo_semana,
            quantidade_posts=p.quantidade_posts, incluir_imagens_ia=p.incluir_imagens_ia,
            ttl_tendencias_horas=p.ttl_tendencias_horas,
            midia_ids_anexadas=tuple(p.midia_ids_anexadas),
            presets_melhoria=tuple(p.presets_melhoria), instrucao_melhoria=p.instrucao_melhoria,
            composicao_formatos=p.composicao_formatos, auto_agendar=p.auto_agendar,
            fuso_horario=p.fuso_horario,
        )
    if payload.tipo_job == TipoJobIA.EXECUTAR_PLANO and payload.executar_plano is not None:
        return payload.executar_plano.model_dump()
    assert payload.recriar_postagem is not None
    return payload.recriar_postagem.model_dump()


@router.post("/jobs", response_model=JobIAResponse, status_code=status.HTTP_202_ACCEPTED)
async def criar_job_ia(
    payload: CriarJobIARequest,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoJobsIAUseCase, Depends(obter_jobs_ia_uc)],
) -> JobIAResponse:
    """Enfileira operação de IA em background com proteção de idempotência."""
    cmd = _converter_cmd(ctx.empresa_id, payload)
    job = await uc.criar_e_agendar(
        empresa_id=ctx.empresa_id,
        conta_ig_id=payload.conta_ig_id,
        tipo_job=payload.tipo_job,
        cmd_ou_dados=cmd,
        chave_idempotencia=payload.chave_idempotencia,
    )
    return _to_job_response(job)


@router.get("/jobs", response_model=list[JobIAResponse])
async def listar_jobs_conta(
    conta_ig_id: Annotated[UUID, Query()],
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoJobsIAUseCase, Depends(obter_jobs_ia_uc)],
    apenas_ativos: bool = False,
) -> list[JobIAResponse]:
    """Lista jobs de IA pertencentes à conta Instagram autenticada."""
    jobs = await uc.listar_jobs_conta(ctx.empresa_id, conta_ig_id, apenas_ativos=apenas_ativos)
    return [_to_job_response(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobIAResponse)
async def consultar_job_ia(
    job_id: UUID,
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    uc: Annotated[ServicoJobsIAUseCase, Depends(obter_jobs_ia_uc)],
) -> JobIAResponse:
    """Consulta status, progresso X/Y e resultado/erro do job do tenant."""
    job = await uc.obter_job(ctx.empresa_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job de IA não encontrado."
        )
    return _to_job_response(job)
