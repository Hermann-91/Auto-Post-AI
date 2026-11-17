"""Caso de uso para recriação contextual (Imagem ou Texto + Cultura RAG) nos cards da Agenda."""

from __future__ import annotations

from uuid import UUID

from app.aplicacao.ia.diretor_arte import DiretorArteService, sanitizar_prompt_visual
from app.aplicacao.ia.dtos import CriarConteudoCmd
from app.aplicacao.ia.dtos_visuais import SceneSpec
from app.aplicacao.ia.geracao_visual import GeradorVisualHibrido
from app.aplicacao.ia.json_ia import extrair_objeto_json
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.publicacao import Postagem
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoMidia
from app.dominio.portas.ia_meta import ClienteIAPort
from app.dominio.portas.repositorios_conteudo import (
    ConfigIARepositoryPort,
    MidiaRepositoryPort,
    PostagemRepositoryPort,
)


class RecriarPostagemContextoUseCase:
    """Recria imagem ou legenda de um post da Agenda somando contexto adicional e Cultura RAG."""

    def __init__(
        self,
        config_repo: ConfigIARepositoryPort,
        midia_repo: MidiaRepositoryPort,
        post_repo: PostagemRepositoryPort,
        cliente_ia: ClienteIAPort,
        orcamento: ServicoOrcamentoUseCase,
        prompts_rag: ServicoPromptsRagUseCase,
        gerador_visual: GeradorVisualHibrido,
        diretor_arte: DiretorArteService | None = None,
    ) -> None:
        self._config_repo = config_repo
        self._midia_repo = midia_repo
        self._post_repo = post_repo
        self._ia = cliente_ia
        self._orcamento = orcamento
        self._prompts_rag = prompts_rag
        self._visual = gerador_visual
        self._diretor = diretor_arte

    async def _obter_post_validado(
        self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID
    ) -> Postagem:
        await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        post = await self._post_repo.buscar_por_id(empresa_id, conta_ig_id, postagem_id)
        if post is None:
            raise ErroValidacaoDominio("Postagem não encontrada nesta conta.")
        return post

    async def substituir_midia_externa(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        postagem_id: UUID,
        nova_midia_id: UUID,
    ) -> Postagem:
        """Substitui a mídia do card da Agenda por uma foto externa (Biblioteca ou PC/Mobile)."""
        post = await self._obter_post_validado(empresa_id, conta_ig_id, postagem_id)
        midia = await self._midia_repo.buscar_por_id(empresa_id, conta_ig_id, nova_midia_id)
        if midia is None:
            raise ErroValidacaoDominio("Mídia externa selecionada não pertence a esta conta.")
        if post.tipo_midia == TipoMidia.CAROUSEL and len(post.midias_chaves) >= 2:
            novas = [midia.chave_storage, *post.midias_chaves[1:]]
        else:
            novas = [midia.chave_storage]
        post.definir_midias(novas)
        return await self._post_repo.salvar(post)

    async def recriar_com_contexto(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        postagem_id: UUID,
        alvo: str,
        contexto_adicional: str,
        presets_melhoria: tuple[str, ...] = (),
        midia_base_id: UUID | None = None,
    ) -> Postagem:
        """Recria 'texto' (com Cultura RAG) ou 'imagem' (via Diretor de Arte) do card."""
        alvo_norm = alvo.strip().lower()
        if alvo_norm not in {"texto", "imagem"}:
            raise ErroValidacaoDominio("Alvo de recriação inválido. Use 'texto' ou 'imagem'.")
        if not contexto_adicional.strip() and not presets_melhoria:
            raise ErroValidacaoDominio(
                "Informe o contexto adicional ou selecione presets de melhoria."
            )

        conta = await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        config = await self._config_repo.obter_ou_padrao(empresa_id, conta_ig_id)
        post = await self._obter_post_validado(empresa_id, conta_ig_id, postagem_id)

        if alvo_norm == "texto":
            chunks_rag = await self._prompts_rag.recuperar_contexto(
                empresa_id, conta_ig_id, f"{post.legenda[:200]} {contexto_adicional}"
            )
            bloco_rag = "\n".join(chunks_rag) if chunks_rag else "Sem fontes RAG adicionais."
            system_prompt = self._prompts_rag.montar_system_prompt(conta, config)
            user_prompt = (
                f"Texto/Legenda atual da postagem:\n{post.legenda}\n\n"
                f"Contexto adicional solicitado pelo usuário:\n{contexto_adicional}\n\n"
                f"Cultura da conta (RAG):\n{bloco_rag}\n\n"
                'Reescreva e melhore a publicação. Retorne JSON com chaves: '
                '"legenda" (string) e "hashtags" (lista de strings).'
            )
            decisao = await self._orcamento.decidir_politica_chamada(
                empresa_id,
                config.modelo_texto_pref,
                estimar_chamada(config.modelo_texto_pref),
                exige_imagem_paga=False,
            )
            bruto, usage = await self._ia.gerar_texto(
                system_prompt, user_prompt, decisao.modelo_efetivo, formato_json=True
            )
            await self._orcamento.registrar_consumo(
                empresa_id, conta_ig_id, usage, postagem_id=post.id
            )
            dados = extrair_objeto_json(bruto)
            nova_legenda = str(dados.get("legenda") or "").strip()
            hashtags = [str(h).strip() for h in (dados.get("hashtags") or []) if str(h).strip()]
            if post.tipo_midia != TipoMidia.STORIES and nova_legenda:
                post.legenda = (
                    f"{nova_legenda}\n\n{' '.join(hashtags)}".strip() if hashtags else nova_legenda
                )
            return await self._post_repo.salvar(post)

        # alvo_norm == "imagem" (sem vazar texto RAG bruto nem duplicar contexto_adicional)
        editar_id = midia_base_id
        todas = await self._midia_repo.listar_por_conta(empresa_id, conta_ig_id)
        if editar_id is None and post.midias_chaves:
            atual = next((m for m in todas if m.chave_storage == post.midias_chaves[0]), None)
            if atual is not None and presets_melhoria:
                editar_id = atual.id

        proporcao = "9:16" if post.tipo_midia == TipoMidia.STORIES else "4:5"
        tema_cena = post.legenda[:180].strip() or "Recriação visual da postagem"
        scene_spec: SceneSpec | None = None
        if self._diretor is not None:
            scene_spec, _, _ = await self._diretor.dirigir_cena(
                conta, config, tema_cena, "recriação visual", post.tipo_midia, proporcao,
                post.legenda[:200], todas, prompt_avancado=contexto_adicional,
                tem_referencia_real=editar_id is not None,
            )
            prompt_cena = scene_spec.prompt_imagem_final
        else:
            prompt_cena = sanitizar_prompt_visual(contexto_adicional or post.legenda[:140])

        cmd_visual = CriarConteudoCmd(
            empresa_id=empresa_id,
            conta_ig_id=conta_ig_id,
            tipo_midia=post.tipo_midia,
            tema=tema_cena,
            gerar_imagem_ia=editar_id is None,
            editar_midia_id=editar_id,
            presets_melhoria=presets_melhoria,
            proporcao=proporcao,
            salvar_rascunho=False,
        )
        res_visual = await self._visual.gerar_e_persistir_com_revisao(
            cmd_visual, config, prompt_visual=prompt_cena, scene_spec=scene_spec
        )
        if post.tipo_midia == TipoMidia.CAROUSEL and len(post.midias_chaves) >= 2:
            novas = [res_visual.midia.chave_storage, *post.midias_chaves[1:]]
        else:
            novas = [res_visual.midia.chave_storage]
        post.definir_midias(novas)
        return await self._post_repo.salvar(post)
