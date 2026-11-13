"""Gestão de Persona, base RAG por conta Instagram e montagem dinâmica de prompts."""

from __future__ import annotations

import re
from uuid import UUID

from app.aplicacao.ia.dtos import AtualizarConfigIACmd, IndexarFonteRagCmd
from app.aplicacao.ia.rag_texto import ranquear_trechos_rag, segmentar_em_chunks
from app.dominio.entidades.ia_rag import ConfigIAConta, FonteRAG
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.portas.repositorios_conteudo import ConfigIARepositoryPort, RagRepositoryPort
from app.dominio.portas.repositorios_tenant import ContaIGRepositoryPort

__all__ = ["ServicoPromptsRagUseCase", "segmentar_em_chunks"]


class ServicoPromptsRagUseCase:
    """Orquestra persona configurável, indexação RAG e recuperação por relevância."""

    def __init__(
        self,
        conta_repo: ContaIGRepositoryPort,
        config_repo: ConfigIARepositoryPort,
        rag_repo: RagRepositoryPort,
    ) -> None:
        self._conta_repo = conta_repo
        self._config_repo = config_repo
        self._rag_repo = rag_repo

    async def exigir_conta(self, empresa_id: UUID, conta_ig_id: UUID) -> ContaInstagram:
        """Valida isolamento multi-tenant garantindo que a conta pertence à empresa."""
        conta = await self._conta_repo.buscar_por_id(empresa_id, conta_ig_id)
        if conta is None:
            raise ErroValidacaoDominio("Conta Instagram não encontrada para esta empresa.")
        return conta

    async def obter_config(self, empresa_id: UUID, conta_ig_id: UUID) -> ConfigIAConta:
        await self.exigir_conta(empresa_id, conta_ig_id)
        return await self._config_repo.obter_ou_padrao(empresa_id, conta_ig_id)

    async def atualizar_config(self, cmd: AtualizarConfigIACmd) -> ConfigIAConta:
        await self.exigir_conta(cmd.empresa_id, cmd.conta_ig_id)
        atual = await self._config_repo.obter_ou_padrao(cmd.empresa_id, cmd.conta_ig_id)
        if not cmd.modelo_texto_pref.strip() or not cmd.modelo_img_pref.strip():
            raise ErroValidacaoDominio("Modelos preferidos de texto e imagem são obrigatórios.")
        atual.persona_json = dict(cmd.persona_json)
        atual.templates_json = dict(cmd.templates_json)
        atual.aplicar_logo_padrao = cmd.aplicar_logo_padrao
        atual.modelo_texto_pref = cmd.modelo_texto_pref.strip()
        atual.modelo_img_pref = cmd.modelo_img_pref.strip()
        return await self._config_repo.salvar(atual)

    async def indexar_fonte(self, cmd: IndexarFonteRagCmd) -> FonteRAG:
        await self.exigir_conta(cmd.empresa_id, cmd.conta_ig_id)
        limpo = re.sub(r"[ \t]+", " ", cmd.conteudo.strip())
        chunks = segmentar_em_chunks(limpo)
        fonte = FonteRAG(
            empresa_id=cmd.empresa_id,
            conta_ig_id=cmd.conta_ig_id,
            tipo=cmd.tipo,
            titulo=cmd.titulo,
            conteudo_limpo=limpo,
            chunks=chunks,
        )
        return await self._rag_repo.salvar(fonte)

    async def listar_fontes(self, empresa_id: UUID, conta_ig_id: UUID) -> list[FonteRAG]:
        await self.exigir_conta(empresa_id, conta_ig_id)
        return await self._rag_repo.listar_por_conta(empresa_id, conta_ig_id)

    async def remover_fonte(self, empresa_id: UUID, conta_ig_id: UUID, fonte_id: UUID) -> bool:
        await self.exigir_conta(empresa_id, conta_ig_id)
        return await self._rag_repo.remover(empresa_id, conta_ig_id, fonte_id)

    async def recuperar_contexto(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        consulta: str,
        top_k: int = 4,
        max_chars: int = 1800,
    ) -> list[str]:
        """Seleciona os chunks mais relevantes ao tema sem truncamento bruto."""
        fontes = await self._rag_repo.listar_por_conta(empresa_id, conta_ig_id)
        return ranquear_trechos_rag(fontes, consulta, top_k=top_k, max_chars=max_chars)

    @staticmethod
    def montar_system_prompt(conta: ContaInstagram, config: ConfigIAConta) -> str:
        """Constrói prompt de sistema dinâmico exclusivamente a partir da conta ativa."""
        p = config.persona_json
        marca = str(p.get("marca") or f"@{conta.username}")
        nicho = str(p.get("nicho") or "criação de conteúdo no Instagram")
        regiao = str(p.get("regiao") or "Brasil")
        tom = str(p.get("tom_voz") or "autêntico, claro e envolvente")
        publico = str(p.get("publico_alvo") or "seguidores engajados")
        cta = str(p.get("cta_padrao") or "convite natural para comentar ou salvar")
        restricoes = str(
            p.get("restricoes") or "não inventar preços, dados ou promessas irreais"
        )
        return (
            f"Você é estrategista de Instagram da conta @{conta.username} ({marca}).\n"
            f"Nicho: {nicho} | Região: {regiao} | Público: {publico}.\n"
            f"Tom de voz: {tom}.\n"
            f"CTA preferencial: {cta}.\n"
            f"Restrições obrigatórias: {restricoes}.\n"
            "Responda sempre em Português do Brasil."
        )

    @staticmethod
    def formatar_ancoras_visuais(midias: list[MidiaBiblioteca], limite: int = 4) -> str:
        """Prioriza mídias curtidas (curtida_favorita=True) como referência estética."""
        ordenadas = sorted(
            midias,
            key=lambda m: (m.curtida_favorita, m.criado_em),
            reverse=True,
        )
        linhas: list[str] = []
        for midia in ordenadas[:limite]:
            tag = "FAVORITA" if midia.curtida_favorita else midia.pasta.value
            desc = midia.resumo_visual.strip() or midia.chave_storage.rsplit("/", 1)[-1]
            linhas.append(f"- [{tag}] {desc}")
        return "\n".join(linhas) if linhas else "Sem referências visuais catalogadas ainda."
