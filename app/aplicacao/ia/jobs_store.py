"""Store assíncrono em memória e serializadores JSON seguros para Jobs de IA."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from app.aplicacao.ia.dtos import ConteudoGeradoDTO, ResultadoExecucaoPlanoDTO
from app.dominio.entidades.job_ia import JobIA, StatusJobIA, TipoJobIA
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import PlanejamentoSemanal, Postagem

_MAX_JOBS_RETIDOS = 500


class JobIAStore:
    """Armazena jobs por ID com índice de isolamento por (empresa_id, conta_ig_id)."""

    def __init__(self, max_itens: int = _MAX_JOBS_RETIDOS) -> None:
        self._max_itens = max(10, max_itens)
        self._jobs: dict[UUID, JobIA] = {}
        self._lock = asyncio.Lock()
        self._tarefas_ativas: set[asyncio.Task[None]] = set()

    async def salvar(self, job: JobIA) -> JobIA:
        async with self._lock:
            self._jobs[job.id] = job
            self._podar_antigos_sem_lock()
            return job

    def _podar_antigos_sem_lock(self) -> None:
        if len(self._jobs) <= self._max_itens:
            return
        finalizados = sorted(
            (j for j in self._jobs.values() if j.finalizado),
            key=lambda j: j.atualizado_em,
        )
        excesso = len(self._jobs) - self._max_itens
        for antigo in finalizados[:excesso]:
            self._jobs.pop(antigo.id, None)

    async def buscar_por_id(self, empresa_id: UUID, job_id: UUID) -> JobIA | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.empresa_id != empresa_id:
                return None
            return job

    async def buscar_ativo_idempotente(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        tipo_job: TipoJobIA,
        chave_idempotencia: str,
    ) -> JobIA | None:
        chave = chave_idempotencia.strip()
        if not chave:
            return None
        async with self._lock:
            for job in self._jobs.values():
                if (
                    job.status != StatusJobIA.FALHA
                    and job.empresa_id == empresa_id
                    and job.conta_ig_id == conta_ig_id
                    and job.tipo_job == tipo_job
                    and job.chave_idempotencia == chave
                ):
                    return job
            return None

    async def listar_por_conta(
        self, empresa_id: UUID, conta_ig_id: UUID, apenas_ativos: bool = False
    ) -> list[JobIA]:
        async with self._lock:
            itens = [
                j
                for j in self._jobs.values()
                if j.empresa_id == empresa_id
                and j.conta_ig_id == conta_ig_id
                and (not apenas_ativos or not j.finalizado)
            ]
            return sorted(itens, key=lambda j: j.criado_em, reverse=True)

    def registrar_task(self, task: asyncio.Task[None]) -> None:
        self._tarefas_ativas.add(task)
        task.add_done_callback(self._tarefas_ativas.discard)

    async def cancelar_tarefas_ativas(self) -> None:
        pendentes = list(self._tarefas_ativas)
        for task in pendentes:
            task.cancel()
        if pendentes:
            await asyncio.gather(*pendentes, return_exceptions=True)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def serializar_postagem(post: Postagem) -> dict[str, Any]:
    return {
        "id": str(post.id),
        "conta_ig_id": str(post.conta_ig_id),
        "tipo_midia": post.tipo_midia.value,
        "midias_chaves": list(post.midias_chaves),
        "legenda": post.legenda,
        "status": post.status.value,
        "planejamento_id": str(post.planejamento_id) if post.planejamento_id else None,
        "agendado_para": _iso(post.agendado_para),
        "meta_container_id": post.meta_container_id,
        "meta_media_id": post.meta_media_id,
        "erro_detalhe": post.erro_detalhe,
        "criado_em": post.criado_em.isoformat(),
        "tentativas_publicacao": post.tentativas_publicacao,
        "atualizado_em": post.atualizado_em.isoformat(),
    }


def serializar_midia(midia: MidiaBiblioteca) -> dict[str, Any]:
    return {
        "id": str(midia.id),
        "pasta": midia.pasta.value,
        "chave_storage": midia.chave_storage,
        "tipo_arquivo": midia.tipo_arquivo,
        "tamanho_bytes": midia.tamanho_bytes,
        "curtida_favorita": midia.curtida_favorita,
        "resumo_visual": midia.resumo_visual,
    }


def serializar_plano(plano: PlanejamentoSemanal) -> dict[str, Any]:
    return {
        "id": str(plano.id),
        "conta_ig_id": str(plano.conta_ig_id),
        "semana_inicio": plano.semana_inicio.isoformat(),
        "status": plano.status.value,
        "custo_estimado_usd": str(plano.custo_estimado_usd),
        "itens_grade": list(plano.itens_grade),
        "tendencias_cache": dict(plano.tendencias_cache),
        "criado_em": plano.criado_em.isoformat(),
    }


def serializar_conteudo(res: ConteudoGeradoDTO) -> dict[str, Any]:
    return {
        "legenda": res.legenda,
        "hashtags": list(res.hashtags),
        "prompt_visual": res.prompt_visual,
        "roteiro_slides": list(res.roteiro_slides),
        "midias_geradas": [serializar_midia(m) for m in res.midias_geradas],
        "postagem": serializar_postagem(res.postagem) if res.postagem else None,
        "custo_total_usd": str(res.custo_total_usd),
        "modelos_usados": list(res.modelos_usados),
        "modo_economico_ativado": res.modo_economico_ativado,
        "qualidade_revisao": res.qualidade_revisao,
        "revisoes_visuais": res.revisoes_visuais,
        "tentativas_geracao_imagem": res.tentativas_geracao_imagem,
        "horario_sugerido": res.horario_sugerido,
    }


def serializar_execucao_plano(res: ResultadoExecucaoPlanoDTO) -> dict[str, Any]:
    return {
        "plano": serializar_plano(res.plano),
        "postagens_criadas": [serializar_postagem(p) for p in res.postagens_criadas],
        "falhas_itens": list(res.falhas_itens),
        "custo_real_usd": str(res.custo_real_usd),
    }
