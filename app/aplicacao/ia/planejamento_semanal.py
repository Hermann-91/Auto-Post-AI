"""Planejamento semanal automatizado em 2 etapas com cache web e estimativa USD."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.aplicacao.ia.agendamento_grade import (
    executar_itens_grade,
    validar_e_expandir_composicao,
    validar_fuso_horario,
)
from app.aplicacao.ia.criar_conteudo import CriarConteudoUseCase
from app.aplicacao.ia.dtos import ProporPlanejamentoCmd, ResultadoExecucaoPlanoDTO
from app.aplicacao.ia.grade_semanal import (
    montar_prompt_grade_semanal,
    normalizar_itens_grade,
)
from app.aplicacao.ia.json_ia import extrair_objeto_json
from app.aplicacao.ia.servico_orcamento import (
    ServicoOrcamentoUseCase,
    estimar_chamada,
    estimar_plano_semanal,
)
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.publicacao import PlanejamentoSemanal
from app.dominio.excecoes import ErroOrcamentoExcedido, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import StatusPlanejamento
from app.dominio.portas.ia_meta import ClienteIAPort, PesquisaTendenciasPort
from app.dominio.portas.repositorios_conteudo import (
    ConfigIARepositoryPort,
    MidiaRepositoryPort,
    PlanejamentoRepositoryPort,
)


class PlanejamentoSemanalUseCase:
    """Orquestra Etapa 1 (proposta + estimativa $) e Etapa 2 (aprovação + execução)."""

    def __init__(
        self,
        config_repo: ConfigIARepositoryPort,
        midia_repo: MidiaRepositoryPort,
        plano_repo: PlanejamentoRepositoryPort,
        cliente_ia: ClienteIAPort,
        tendencias: PesquisaTendenciasPort,
        orcamento: ServicoOrcamentoUseCase,
        prompts_rag: ServicoPromptsRagUseCase,
        criador_conteudo: CriarConteudoUseCase,
    ) -> None:
        self._config_repo = config_repo
        self._midia_repo = midia_repo
        self._plano_repo = plano_repo
        self._ia = cliente_ia
        self._tendencias = tendencias
        self._orcamento = orcamento
        self._prompts_rag = prompts_rag
        self._criador = criador_conteudo

    async def propor_semana(self, cmd: ProporPlanejamentoCmd) -> PlanejamentoSemanal:
        """Etapa 1: consulta cache web/RAG/favoritas, gera grade JSON e estima USD."""
        qtd_total, formatos_seq = validar_e_expandir_composicao(
            cmd.composicao_formatos, cmd.quantidade_posts
        )
        zona = validar_fuso_horario(cmd.fuso_horario)
        conta = await self._prompts_rag.exigir_conta(cmd.empresa_id, cmd.conta_ig_id)
        config = await self._config_repo.obter_ou_padrao(cmd.empresa_id, cmd.conta_ig_id)

        nicho = cmd.nicho.strip() or str(config.persona_json.get("nicho") or "marketing digital")
        regiao = cmd.regiao.strip() or str(config.persona_json.get("regiao") or "Brasil")
        tendencias = await self._tendencias.buscar_tendencias(
            nicho=nicho, regiao=regiao, ttl_horas=cmd.ttl_tendencias_horas
        )
        chunks = await self._prompts_rag.recuperar_contexto(
            cmd.empresa_id, cmd.conta_ig_id, f"{nicho} {cmd.objetivo_semana}"
        )
        midias = await self._midia_repo.listar_por_conta(cmd.empresa_id, cmd.conta_ig_id)
        ancoras = self._prompts_rag.formatar_ancoras_visuais(midias)

        system_prompt = self._prompts_rag.montar_system_prompt(conta, config)
        user_prompt = montar_prompt_grade_semanal(
            cmd, nicho, regiao, tendencias, chunks, ancoras, formatos_seq or None
        )

        decisao = await self._orcamento.decidir_politica_chamada(
            cmd.empresa_id,
            config.modelo_texto_pref,
            estimar_chamada(config.modelo_texto_pref),
            exige_imagem_paga=False,
        )
        bruto, usage = await self._ia.gerar_texto(
            system_prompt, user_prompt, decisao.modelo_efetivo, formato_json=True
        )
        await self._orcamento.registrar_consumo(cmd.empresa_id, cmd.conta_ig_id, usage)

        dados = extrair_objeto_json(bruto)
        brutos = dados.get("itens")
        if not isinstance(brutos, list):
            raise ErroValidacaoDominio("Grade semanal retornada pela IA não contém lista 'itens'.")
        itens = normalizar_itens_grade(
            brutos, qtd_total, cmd.incluir_imagens_ia, formatos_seq or None
        )
        custo_est = estimar_plano_semanal(itens, config.modelo_texto_pref, config.modelo_img_pref)
        tendencias_salvas = {
            **tendencias,
            "_config_plano": {
                "auto_agendar": cmd.auto_agendar,
                "fuso_horario": str(zona),
                "composicao_formatos": cmd.composicao_formatos or {},
            },
        }

        plano = PlanejamentoSemanal(
            empresa_id=cmd.empresa_id, conta_ig_id=cmd.conta_ig_id,
            semana_inicio=cmd.semana_inicio, itens_grade=itens,
            tendencias_cache=tendencias_salvas, custo_estimado_usd=custo_est,
        )
        plano.enviar_para_aprovacao()
        return await self._plano_repo.salvar(plano)

    async def aprovar_plano(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        plano_id: UUID,
    ) -> PlanejamentoSemanal:
        """Etapa 2a: valida orçamento estimado e aprova plano para execução/Worker."""
        plano = await self.obter_plano(empresa_id, conta_ig_id, plano_id)
        disponivel = await self._orcamento.verificar_disponibilidade(
            empresa_id, plano.custo_estimado_usd
        )
        if not disponivel:
            raise ErroOrcamentoExcedido(
                "Orçamento mensal insuficiente para executar este planejamento semanal."
            )
        plano.aprovar()
        return await self._plano_repo.salvar(plano)

    async def executar_plano(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        plano_id: UUID,
        auto_agendar: bool | None = None,
        fuso_horario: str | None = None,
    ) -> ResultadoExecucaoPlanoDTO:
        """Etapa 2b: executa os itens aprovados gerando mídias IA e rascunhos."""
        plano = await self.obter_plano(empresa_id, conta_ig_id, plano_id)
        if plano.status in {StatusPlanejamento.CONCLUIDO, StatusPlanejamento.FALHA}:
            plano.status = StatusPlanejamento.APROVADO
            for it in plano.itens_grade:
                if isinstance(it, dict):
                    it["usar_ia_imagem"] = True
        plano.iniciar_execucao()
        await self._plano_repo.salvar(plano)

        postagens, falhas, custo_real = await executar_itens_grade(
            plano, self._criador, auto_agendar, fuso_horario
        )

        if falhas and not postagens and custo_real == Decimal("0"):
            plano.marcar_falha()
        else:
            plano.concluir()
        plano_final = await self._plano_repo.salvar(plano)
        return ResultadoExecucaoPlanoDTO(
            plano=plano_final,
            postagens_criadas=postagens,
            falhas_itens=falhas,
            custo_real_usd=custo_real,
        )

    async def obter_plano(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        plano_id: UUID,
    ) -> PlanejamentoSemanal:
        await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        plano = await self._plano_repo.buscar_por_id(empresa_id, conta_ig_id, plano_id)
        if plano is None:
            raise ErroValidacaoDominio("Planejamento semanal não encontrado para esta conta.")
        return plano

    async def listar_planos(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
    ) -> list[PlanejamentoSemanal]:
        await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        return await self._plano_repo.listar_por_conta(empresa_id, conta_ig_id)
