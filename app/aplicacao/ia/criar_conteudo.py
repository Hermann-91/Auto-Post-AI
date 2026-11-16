"""Caso de uso de geração de conteúdo individual e pipeline visual híbrido."""

from __future__ import annotations

from typing import Any

from app.aplicacao.ia.diretor_arte import DiretorArteService, sanitizar_prompt_visual
from app.aplicacao.ia.dtos import ConteudoGeradoDTO, CriarConteudoCmd
from app.aplicacao.ia.dtos_visuais import SceneSpec
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.json_ia import extrair_objeto_json
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.ia_rag import ConfigIAConta
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.publicacao import Postagem
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem, TipoMidia
from app.dominio.portas.ia_meta import ClienteIAPort
from app.dominio.portas.repositorios_conteudo import (
    ConfigIARepositoryPort,
    MidiaRepositoryPort,
    PostagemRepositoryPort,
)


class CriarConteudoUseCase:
    """Orquestra texto, Nano Banana opcional, pipeline Pillow $0 e rascunho Meta."""

    def __init__(
        self,
        config_repo: ConfigIARepositoryPort,
        midia_repo: MidiaRepositoryPort,
        post_repo: PostagemRepositoryPort,
        cliente_ia: ClienteIAPort,
        orcamento: ServicoOrcamentoUseCase,
        prompts_rag: ServicoPromptsRagUseCase,
        gerador_visual: GeradorVisualHibrido,
        cota_midia: CotaMidia | None = None,
        diretor_arte: DiretorArteService | None = None,
    ) -> None:
        self._config_repo, self._midia_repo, self._post_repo = config_repo, midia_repo, post_repo
        self._ia, self._orcamento, self._prompts_rag = cliente_ia, orcamento, prompts_rag
        self._visual = gerador_visual
        self._cota = cota_midia or CotaMidia()
        self._diretor = diretor_arte

    async def _validar_pre_condicoes(
        self,
        cmd: CriarConteudoCmd,
        config: ConfigIAConta,
    ) -> tuple[bool, list[MidiaBiblioteca]]:
        if not cmd.tema.strip():
            raise ErroValidacaoDominio("Tema do conteúdo é obrigatório.")
        usa_ia_visual = cmd.gerar_imagem_ia or cmd.editar_midia_id is not None
        if usa_ia_visual and cmd.tipo_midia == TipoMidia.REELS:
            raise ErroValidacaoDominio("Geração de imagem IA não se aplica ao formato REELS.")

        bases: list[MidiaBiblioteca] = []
        for midia_id in cmd.midia_base_ids:
            m = await self._midia_repo.buscar_por_id(cmd.empresa_id, cmd.conta_ig_id, midia_id)
            if m is None:
                raise ErroValidacaoDominio("Mídia base informada não pertence a esta conta.")
            bases.append(m)

        if usa_ia_visual:
            qtd, bytes_usados = await self._midia_repo.calcular_uso_cota(
                cmd.empresa_id, cmd.conta_ig_id
            )
            self._cota.validar_novo_arquivo(qtd, bytes_usados, novo_tamanho_bytes=1)
            modelo_img = (cmd.modelo_imagem or config.modelo_img_pref).strip()
            await self._orcamento.decidir_politica_chamada(
                cmd.empresa_id,
                modelo_img,
                estimar_chamada(modelo_img, eh_imagem=True),
                exige_imagem_paga=True,
            )

        if cmd.salvar_rascunho and cmd.tipo_midia == TipoMidia.CAROUSEL:
            total_itens = len(bases) + (1 if usa_ia_visual else 0)
            if not 2 <= total_itens <= 10:
                raise ErroValidacaoDominio("Carrossel exige entre 2 e 10 mídias para rascunho.")
        return usa_ia_visual, bases

    def _montar_prompt_copywriter(
        self, cmd: CriarConteudoCmd, rag_bloco: str, todas_midias: list[MidiaBiblioteca]
    ) -> str:
        bloco_pilar = f" | Pilar: {cmd.pilar_editorial}" if cmd.pilar_editorial.strip() else ""
        bloco_serie = (
            f"\nSérie narrativa ativa (etapa: {cmd.etapa_serie or 'sequencial'})."
            if cmd.modo_serie
            else ""
        )
        base = (
            f"Formato: {cmd.tipo_midia.value} | Tema: {cmd.tema} | "
            f"Objetivo: {cmd.objetivo}{bloco_pilar}\n"
            f"Instrução extra de tom: {cmd.tom_extra or 'padrão da conta'}{bloco_serie}\n"
            f"Base de conhecimento:\n{rag_bloco}\n"
        )
        if self._diretor is not None:
            return (
                f"{base}"
                'Retorne JSON com chaves: "legenda" (string vazia se STORIES), '
                '"hashtags" (lista de strings), "roteiro_slides" (lista de strings).'
            )
        ancoras = self._prompts_rag.formatar_ancoras_visuais(
            todas_midias, modo_serie=cmd.modo_serie
        )
        return (
            f"{base}Memória visual da conta:\n{ancoras}\n"
            'Retorne JSON com chaves: "legenda" (string vazia se STORIES), '
            '"hashtags" (lista de strings), "prompt_visual" (string descritiva), '
            '"roteiro_slides" (lista de strings).'
        )

    async def executar(self, cmd: CriarConteudoCmd) -> ConteudoGeradoDTO:
        """Gera legenda/roteiro, imagem IA opcional com pós-processamento e rascunho."""
        conta = await self._prompts_rag.exigir_conta(cmd.empresa_id, cmd.conta_ig_id)
        config = await self._config_repo.obter_ou_padrao(cmd.empresa_id, cmd.conta_ig_id)
        usa_ia_visual, bases = await self._validar_pre_condicoes(cmd, config)

        chunks = await self._prompts_rag.recuperar_contexto(
            cmd.empresa_id, cmd.conta_ig_id, f"{cmd.tema} {cmd.objetivo}"
        )
        todas_midias = await self._midia_repo.listar_por_conta(cmd.empresa_id, cmd.conta_ig_id)
        rag_bloco = "\n".join(chunks) if chunks else "Sem documentos RAG adicionais."
        system_prompt = self._prompts_rag.montar_system_prompt(conta, config)
        user_prompt = self._montar_prompt_copywriter(cmd, rag_bloco, todas_midias)

        modelo_txt = (cmd.modelo_texto or config.modelo_texto_pref).strip()
        decisao_txt = await self._orcamento.decidir_politica_chamada(
            cmd.empresa_id, modelo_txt, estimar_chamada(modelo_txt), exige_imagem_paga=False
        )
        bruto_txt, usage_txt = await self._ia.gerar_texto(
            system_prompt, user_prompt, decisao_txt.modelo_efetivo, formato_json=True
        )
        reg_txt = await self._orcamento.registrar_consumo(
            cmd.empresa_id, cmd.conta_ig_id, usage_txt
        )
        estruturado = extrair_objeto_json(bruto_txt)

        eh_stories = cmd.tipo_midia == TipoMidia.STORIES
        legenda = "" if eh_stories else str(estruturado.get("legenda") or "").strip()
        hashtags = [str(h) for h in estruturado.get("hashtags") or [] if str(h).strip()]
        roteiro = [str(s) for s in estruturado.get("roteiro_slides") or [] if str(s).strip()]

        custo_total, modelos_usados = reg_txt.custo_usd, [reg_txt.modelo]
        prompt_visual = sanitizar_prompt_visual(
            str(estruturado.get("prompt_visual") or cmd.prompt_avancado or cmd.tema)
        )
        scene_spec: SceneSpec | None = None
        if usa_ia_visual and self._diretor is not None:
            scene_spec, custo_da, modelo_da = await self._diretor.dirigir_cena(
                conta, config, cmd.tema, cmd.objetivo, cmd.tipo_midia, cmd.proporcao,
                legenda or cmd.tema, todas_midias, cmd.pilar_editorial, cmd.modo_serie,
                cmd.etapa_serie, cmd.prompt_avancado or cmd.prompt_visual_extra,
                bool(bases or cmd.editar_midia_id is not None), cmd.modelo_texto,
            )
            custo_total += custo_da
            modelos_usados.append(modelo_da)
            prompt_visual = scene_spec.prompt_imagem_final

        midias_geradas: list[MidiaBiblioteca] = []
        chaves_post = [m.chave_storage for m in bases]
        qualidade_revisao: dict[str, Any] | None = None
        revisoes_visuais, tentativas_img = 0, 0
        if usa_ia_visual:
            res_vis = await self._visual.gerar_e_persistir_com_revisao(
                cmd, config, prompt_visual, scene_spec=scene_spec
            )
            midias_geradas.append(res_vis.midia)
            chaves_post.append(res_vis.midia.chave_storage)
            custo_total += res_vis.custo_total_usd
            modelos_usados.extend(res_vis.modelos_usados)
            qualidade_revisao = res_vis.qualidade_revisao.para_dict()
            revisoes_visuais = res_vis.qualidade_revisao.revisoes_critico
            tentativas_img = res_vis.qualidade_revisao.tentativas_geracao

        postagem: Postagem | None = None
        if cmd.salvar_rascunho and chaves_post:
            legenda_post = (
                "" if eh_stories
                else (f"{legenda}\n\n{' '.join(hashtags)}".strip() if hashtags else legenda)
            )
            postagem = await self._post_repo.salvar(Postagem(
                empresa_id=cmd.empresa_id, conta_ig_id=cmd.conta_ig_id,
                tipo_midia=cmd.tipo_midia, midias_chaves=chaves_post, legenda=legenda_post,
                status=StatusPostagem.RASCUNHO, planejamento_id=cmd.planejamento_id,
            ))

        return ConteudoGeradoDTO(
            legenda=legenda, hashtags=hashtags, prompt_visual=prompt_visual,
            roteiro_slides=roteiro, midias_geradas=midias_geradas, postagem=postagem,
            custo_total_usd=custo_total, modelos_usados=modelos_usados,
            modo_economico_ativado=decisao_txt.modo_economico_ativado,
            qualidade_revisao=qualidade_revisao, revisoes_visuais=revisoes_visuais,
            tentativas_geracao_imagem=tentativas_img,
        )
