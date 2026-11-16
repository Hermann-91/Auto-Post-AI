"""Caso de uso para encaixar mídias anexadas na semana e editar o Resumo/Orçamento."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.aplicacao.ia.grade_semanal import normalizar_formato_midia
from app.aplicacao.ia.servico_orcamento import estimar_plano_semanal
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.publicacao import PlanejamentoSemanal
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import StatusPlanejamento
from app.dominio.portas.repositorios_conteudo import (
    ConfigIARepositoryPort,
    MidiaRepositoryPort,
    PlanejamentoRepositoryPort,
)


class EdicaoOrcamentoSemanalUseCase:
    """Encaixa fotos anexadas na grade semanal e permite editar itens antes de concluir."""

    def __init__(
        self,
        config_repo: ConfigIARepositoryPort,
        midia_repo: MidiaRepositoryPort,
        plano_repo: PlanejamentoRepositoryPort,
        prompts_rag: ServicoPromptsRagUseCase,
    ) -> None:
        self._config_repo = config_repo
        self._midia_repo = midia_repo
        self._plano_repo = plano_repo
        self._prompts_rag = prompts_rag

    async def encaixar_midias_na_semana(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        plano: PlanejamentoSemanal,
        midia_ids: tuple[UUID, ...],
        presets_melhoria: tuple[str, ...] = (),
        instrucao_melhoria: str = "",
    ) -> PlanejamentoSemanal:
        """Associa fotos anexadas pelo usuário aos itens da semana para edição/melhoria IA."""
        if not midia_ids:
            return plano
        await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        config = await self._config_repo.obter_ou_padrao(empresa_id, conta_ig_id)

        midias_validas = []
        for midia_id in midia_ids:
            m = await self._midia_repo.buscar_por_id(empresa_id, conta_ig_id, midia_id)
            if m is None:
                raise ErroValidacaoDominio("Uma das imagens anexadas não pertence a esta conta.")
            midias_validas.append(m)

        usar_edicao_ia = bool(presets_melhoria or instrucao_melhoria.strip())
        for idx, midia in enumerate(midias_validas):
            if idx >= len(plano.itens_grade):
                break
            item = plano.itens_grade[idx]
            resumo_foto = midia.resumo_visual.strip() or "Foto anexada da conta"
            if usar_edicao_ia:
                item["editar_midia_id"] = str(midia.id)
                item["midia_base_ids"] = []
                item["usar_ia_imagem"] = True
                item["presets_melhoria"] = list(presets_melhoria)
                extra = (
                    f" | Melhoria solicitada: {instrucao_melhoria.strip()}"
                    if instrucao_melhoria.strip()
                    else ""
                )
                item["ideia_visual"] = (
                    f"{item.get('ideia_visual', '')} (Base: {resumo_foto}{extra})".strip()
                )
            else:
                item["editar_midia_id"] = None
                item["midia_base_ids"] = [str(midia.id)]
                item["usar_ia_imagem"] = False
                item["presets_melhoria"] = []

        plano.custo_estimado_usd = estimar_plano_semanal(
            plano.itens_grade, config.modelo_texto_pref, config.modelo_img_pref
        )
        return await self._plano_repo.salvar(plano)

    async def atualizar_itens_orcamento(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        plano_id: UUID,
        itens_editados: list[dict[str, Any]],
    ) -> PlanejamentoSemanal:
        """Salva edições feitas pelo usuário no Resumo/Orçamento e recalcula o custo estimado."""
        await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        plano = await self._plano_repo.buscar_por_id(empresa_id, conta_ig_id, plano_id)
        if plano is None:
            raise ErroValidacaoDominio("Planejamento semanal não encontrado para esta conta.")
        if plano.status not in {
            StatusPlanejamento.AGUARDANDO_APROVACAO,
            StatusPlanejamento.APROVADO,
            StatusPlanejamento.RASCUNHO,
        }:
            raise ErroValidacaoDominio(
                f"Não é possível editar itens de um plano com status '{plano.status.value}'."
            )
        if not itens_editados:
            raise ErroValidacaoDominio("A grade semanal deve conter ao menos 1 publicação no resumo.")

        config = await self._config_repo.obter_ou_padrao(empresa_id, conta_ig_id)
        novos_itens: list[dict[str, Any]] = []
        for idx, bruto in enumerate(itens_editados, start=1):
            formato = normalizar_formato_midia(bruto.get("formato"))
            editar_id = bruto.get("editar_midia_id")
            usar_ia = bool(bruto.get("usar_ia_imagem", False)) or bool(editar_id)
            novos_itens.append(
                {
                    "ordem": idx,
                    "dia_semana": str(bruto.get("dia_semana") or f"Dia {idx}").strip(),
                    "horario_sugerido": str(bruto.get("horario_sugerido") or "18:00").strip(),
                    "formato": formato.value,
                    "tema": str(bruto.get("tema") or f"Publicação {idx}").strip(),
                    "objetivo": str(bruto.get("objetivo") or "engajamento").strip(),
                    "gancho": str(bruto.get("gancho") or "").strip(),
                    "ideia_visual": str(bruto.get("ideia_visual") or "").strip(),
                    "legenda_previa": str(bruto.get("legenda_previa") or "").strip(),
                    "usar_ia_imagem": usar_ia,
                    "editar_midia_id": str(editar_id) if editar_id else None,
                    "midia_base_ids": [str(m) for m in (bruto.get("midia_base_ids") or []) if m],
                    "presets_melhoria": [str(p) for p in (bruto.get("presets_melhoria") or []) if p],
                }
            )

        plano.itens_grade = novos_itens
        plano.custo_estimado_usd = estimar_plano_semanal(
            novos_itens, config.modelo_texto_pref, config.modelo_img_pref
        )
        return await self._plano_repo.salvar(plano)
