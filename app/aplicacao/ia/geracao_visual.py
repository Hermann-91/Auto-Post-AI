"""Auxiliar de geração/edição Nano Banana com crítica VLM e pipeline $0."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from app.aplicacao.ia.avaliador_visual import AvaliadorVisualCritico
from app.aplicacao.ia.diretor_arte import (
    MAPA_PROMPT_PRESETS,
    compilar_prompt_geracao,
    sanitizar_prompt_visual,
)
from app.aplicacao.ia.dtos import (
    CompactadorMiniaturaPort,
    CriarConteudoCmd,
    PipelineMidiaPort,
)
from app.aplicacao.ia.dtos_visuais import (
    QualidadeRevisaoVisual,
    ResultadoGeracaoVisual,
    SceneSpec,
    VereditoCriticoVisual,
)
from app.aplicacao.ia.persistencia_visual import (
    pos_processar_e_salvar_midia,
    preparar_referencias_visuais_conta,
)
from app.aplicacao.ia.servico_orcamento import (
    MAX_LOOPS_CRITICA_VISUAL,
    ServicoOrcamentoUseCase,
    estimar_chamada,
    estimar_pipeline_visual,
)
from app.dominio.entidades.ia_rag import ConfigIAConta
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.excecoes import ErroOrcamentoExcedido
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.dominio.portas.ia_meta import (
    ClienteIAPort,
    ClienteImagemMultireferenciaPort,
    ClienteVisaoPort,
)
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort

__all__ = ["MAPA_PROMPT_PRESETS", "GeradorVisualHibrido"]


class GeradorVisualHibrido:
    """Executa Nano Banana, crítica visual VLM (máx 2 loops) e pós-processamento ($0)."""

    def __init__(
        self,
        midia_repo: MidiaRepositoryPort,
        storage: StorageMidiaPort,
        cliente_ia: ClienteIAPort,
        orcamento: ServicoOrcamentoUseCase,
        pipeline_midia: PipelineMidiaPort,
        compactador: CompactadorMiniaturaPort,
        cota_midia: CotaMidia | None = None,
        cliente_visao: ClienteVisaoPort | None = None,
        modelo_visao: str = "google/gemini-2.5-flash-lite",
        avaliador_visual: AvaliadorVisualCritico | None = None,
    ) -> None:
        self._midia_repo, self._storage, self._ia = midia_repo, storage, cliente_ia
        self._orcamento, self._pipeline, self._compactar = orcamento, pipeline_midia, compactador
        self._cota = cota_midia or CotaMidia()
        self._avaliador = avaliador_visual or (
            AvaliadorVisualCritico(cliente_visao, orcamento, compactador, modelo_visao)
            if cliente_visao is not None
            else None
        )

    async def gerar_e_persistir(
        self, cmd: CriarConteudoCmd, config: ConfigIAConta, prompt_visual: str
    ) -> tuple[MidiaBiblioteca, Decimal, str]:
        """Wrapper retrocompatível retornando (midia, custo_total_usd, modelo_imagem)."""
        res = await self.gerar_e_persistir_com_revisao(cmd, config, prompt_visual)
        modelo_img = next((m for m in res.modelos_usados if m), config.modelo_img_pref)
        return res.midia, res.custo_total_usd, modelo_img

    async def gerar_e_persistir_com_revisao(
        self, cmd: CriarConteudoCmd, config: ConfigIAConta,
        prompt_visual: str, scene_spec: SceneSpec | None = None,
    ) -> ResultadoGeracaoVisual:
        """Gera/edita com múltiplas referências, crítica em até 2 loops e Pillow."""
        modelo_img = (cmd.modelo_imagem or config.modelo_img_pref).strip()
        teto = (
            estimar_pipeline_visual(
                modelo_img, self._avaliador.modelo_padrao, incluir_regeneracao=False
            )
            if self._avaliador is not None
            else estimar_chamada(modelo_img, eh_imagem=True)
        )
        decisao = await self._orcamento.decidir_politica_chamada(
            cmd.empresa_id, modelo_img, teto, exige_imagem_paga=True
        )
        refs_urls, pasta_destino = await preparar_referencias_visuais_conta(
            self._midia_repo, self._storage, self._compactar, cmd
        )
        img_bytes, custo, modelos, revisao, prompt_usado = await self._executar_loop_visual(
            cmd, decisao.modelo_efetivo, prompt_visual, refs_urls, scene_spec
        )
        resumo = (
            scene_spec.resumo_anti_repeticao()
            if scene_spec is not None
            else sanitizar_prompt_visual(prompt_visual)
        )[:300]
        midia = await pos_processar_e_salvar_midia(
            self._midia_repo, self._storage, self._pipeline, self._cota,
            cmd, config, img_bytes, pasta_destino, resumo,
        )
        return ResultadoGeracaoVisual(
            midia=midia, custo_total_usd=custo, modelos_usados=modelos,
            qualidade_revisao=revisao, prompt_final_usado=prompt_usado,
        )

    async def _executar_loop_visual(
        self, cmd: CriarConteudoCmd, modelo_efetivo: str, prompt_visual: str,
        refs_urls: list[str], scene_spec: SceneSpec | None,
    ) -> tuple[bytes, Decimal, list[str], QualidadeRevisaoVisual, str]:
        custo_total, modelos_usados, diagnosticos = Decimal("0"), [], []
        correcao, img_escolhida, prompt_usado = "", b"", ""
        ultimo_veredito: VereditoCriticoVisual | None = None
        tentativas, revisoes = 0, 0
        for tentativa in range(1, MAX_LOOPS_CRITICA_VISUAL + 1):
            if tentativa > 1:
                try:
                    await self._orcamento.decidir_politica_chamada(
                        cmd.empresa_id, modelo_efetivo,
                        estimar_chamada(modelo_efetivo, eh_imagem=True), exige_imagem_paga=True,
                    )
                except ErroOrcamentoExcedido:
                    break
            prompt_usado = compilar_prompt_geracao(
                prompt_visual, cmd.prompt_avancado, cmd.prompt_visual_extra,
                cmd.presets_melhoria, correcao,
            )
            img_bytes, usage = await self._chamar_gerador_imagem(
                prompt_usado, modelo_efetivo, refs_urls
            )
            reg = await self._orcamento.registrar_consumo(cmd.empresa_id, cmd.conta_ig_id, usage)
            custo_total += reg.custo_usd
            modelos_usados.append(reg.modelo)
            img_escolhida, tentativas = img_bytes, tentativa
            if self._avaliador is None:
                return img_escolhida, custo_total, modelos_usados, QualidadeRevisaoVisual(
                    aprovado=True, tentativas_geracao=tentativas, revisoes_critico=0,
                    modo_serie=cmd.modo_serie, etapa_serie=cmd.etapa_serie,
                    pilar_editorial=cmd.pilar_editorial,
                ), prompt_usado
            veredito = await self._avaliador.avaliar_imagem(
                cmd.empresa_id, cmd.conta_ig_id, img_bytes,
                scene_spec if scene_spec is not None else prompt_usado,
            )
            revisoes, ultimo_veredito = revisoes + 1, veredito
            custo_total += veredito.custo_usd
            if veredito.modelo_usado:
                modelos_usados.append(veredito.modelo_usado)
            if veredito.aprovado:
                break
            if veredito.diagnostico_correcao:
                diagnosticos.append(veredito.diagnostico_correcao)
                correcao = veredito.diagnostico_correcao
        revisao = QualidadeRevisaoVisual(
            aprovado=ultimo_veredito.aprovado if ultimo_veredito else True,
            tentativas_geracao=tentativas, revisoes_critico=revisoes,
            ultimo_veredito=ultimo_veredito, historico_diagnosticos=tuple(diagnosticos),
            modo_serie=cmd.modo_serie, etapa_serie=cmd.etapa_serie,
            pilar_editorial=cmd.pilar_editorial,
        )
        return img_escolhida, custo_total, modelos_usados, revisao, prompt_usado

    async def _chamar_gerador_imagem(
        self, prompt: str, modelo: str, refs_urls: list[str]
    ) -> tuple[bytes, dict[str, Any]]:
        if len(refs_urls) > 1 and callable(getattr(self._ia, "gerar_imagem_com_referencias", None)):
            multi = cast(ClienteImagemMultireferenciaPort, self._ia)
            return await multi.gerar_imagem_com_referencias(prompt, modelo, refs_urls)
        return await self._ia.gerar_ou_editar_imagem(
            prompt=prompt, modelo=modelo, imagem_base_url=refs_urls[0] if refs_urls else None
        )
