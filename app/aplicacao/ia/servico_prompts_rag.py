"""Gestão de Persona, Brand Bible, base RAG híbrida e prompts por conta."""

from __future__ import annotations

import logging
import re
from uuid import UUID

from app.aplicacao.ia.dtos import (
    AtualizarConfigIACmd,
    IndexarArquivoRagCmd,
    IndexarFonteRagCmd,
    IndexarUrlRagCmd,
)
from app.aplicacao.ia.prompts_brand_bible import (
    compilar_brand_bible_deterministica,
    enriquecer_brand_bible_com_ia,
    formatar_ancoras_visuais_lista,
    montar_system_prompt_com_brand_bible,
)
from app.aplicacao.ia.rag_texto import gerar_resumo_fatos, ranquear_trechos_rag, segmentar_em_chunks
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.dominio.entidades.ia_rag import ConfigIAConta, FonteRAG
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroDominio, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoFonteRAG
from app.dominio.portas.ia_meta import (
    ClienteEmbeddingsPort,
    ClienteIAPort,
    ExtratorConteudoRagPort,
)
from app.dominio.portas.repositorios_conteudo import ConfigIARepositoryPort, RagRepositoryPort
from app.dominio.portas.repositorios_tenant import ContaIGRepositoryPort

logger = logging.getLogger(__name__)
__all__ = ["ServicoPromptsRagUseCase", "segmentar_em_chunks"]


class ServicoPromptsRagUseCase:
    """Orquestra persona, Brand Bible, indexação RAG híbrida e recuperação por conta."""

    def __init__(
        self, conta_repo: ContaIGRepositoryPort, config_repo: ConfigIARepositoryPort,
        rag_repo: RagRepositoryPort, cliente_embeddings: ClienteEmbeddingsPort | None = None,
        extrator_rag: ExtratorConteudoRagPort | None = None,
        orcamento: ServicoOrcamentoUseCase | None = None,
        modelo_embeddings: str = "openai/text-embedding-3-small",
        cliente_ia: ClienteIAPort | None = None,
    ) -> None:
        self._conta_repo, self._config_repo, self._rag_repo = conta_repo, config_repo, rag_repo
        self._embeddings, self._extrator = cliente_embeddings, extrator_rag
        self._orcamento, self._ia = orcamento, cliente_ia
        self._modelo_embeddings = modelo_embeddings

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
        conta = await self.exigir_conta(cmd.empresa_id, cmd.conta_ig_id)
        atual = await self._config_repo.obter_ou_padrao(cmd.empresa_id, cmd.conta_ig_id)
        if not cmd.modelo_texto_pref.strip() or not cmd.modelo_img_pref.strip():
            raise ErroValidacaoDominio("Modelos preferidos de texto e imagem são obrigatórios.")
        atual.persona_json, atual.templates_json = dict(cmd.persona_json), dict(cmd.templates_json)
        if cmd.brand_bible_json is not None:
            atual.brand_bible_json = dict(cmd.brand_bible_json)
        atual.aplicar_logo_padrao = cmd.aplicar_logo_padrao
        atual.modelo_texto_pref = cmd.modelo_texto_pref.strip()
        atual.modelo_img_pref = cmd.modelo_img_pref.strip()
        fontes = await self._rag_repo.listar_por_conta(cmd.empresa_id, cmd.conta_ig_id)
        atual.brand_bible_json = compilar_brand_bible_deterministica(conta, atual, fontes)
        return await self._config_repo.salvar(atual)

    async def _gerar_embeddings_seguro(
        self, empresa_id: UUID, conta_ig_id: UUID, textos: list[str]
    ) -> list[list[float]]:
        if self._embeddings is None or not textos:
            return []
        try:
            modelo = self._modelo_embeddings
            orc = self._orcamento
            if orc is not None:
                await orc.decidir_politica_chamada(empresa_id, modelo, estimar_chamada(modelo))
            vetores, usage = await self._embeddings.gerar_embeddings(textos, modelo)
            if orc is not None:
                await orc.registrar_consumo(empresa_id, conta_ig_id, usage)
            return vetores if len(vetores) == len(textos) else []
        except ErroDominio as exc:
            logger.warning("Embeddings RAG ignorados (fallback lexical): %s", exc)
            return []

    async def _sincronizar_brand_bible(self, conta: ContaInstagram) -> None:
        config = await self._config_repo.obter_ou_padrao(conta.empresa_id, conta.id)
        fontes = await self._rag_repo.listar_por_conta(conta.empresa_id, conta.id)
        config.brand_bible_json = compilar_brand_bible_deterministica(conta, config, fontes)
        await self._config_repo.salvar(config)

    async def compilar_brand_bible(
        self, empresa_id: UUID, conta_ig_id: UUID, usar_ia: bool = False
    ) -> ConfigIAConta:
        """Compila e persiste Brand Bible da conta (determinística ou via IA)."""
        conta = await self.exigir_conta(empresa_id, conta_ig_id)
        config = await self._config_repo.obter_ou_padrao(empresa_id, conta_ig_id)
        fontes = await self._rag_repo.listar_por_conta(empresa_id, conta_ig_id)
        base = compilar_brand_bible_deterministica(conta, config, fontes)
        if usar_ia and self._ia is not None:
            base = await enriquecer_brand_bible_com_ia(
                conta, config, base, self._ia, self._orcamento
            )
        config.brand_bible_json = base
        return await self._config_repo.salvar(config)

    async def indexar_fonte(self, cmd: IndexarFonteRagCmd) -> FonteRAG:
        conta = await self.exigir_conta(cmd.empresa_id, cmd.conta_ig_id)
        limpo = re.sub(r"[ \t]+", " ", cmd.conteudo.strip())
        chunks = segmentar_em_chunks(limpo)
        resumo = cmd.resumo_fatos.strip() or gerar_resumo_fatos(cmd.titulo, limpo)
        vetores = await self._gerar_embeddings_seguro(cmd.empresa_id, cmd.conta_ig_id, chunks)
        fonte = FonteRAG(
            empresa_id=cmd.empresa_id, conta_ig_id=cmd.conta_ig_id, tipo=cmd.tipo,
            titulo=cmd.titulo, conteudo_limpo=limpo, chunks=chunks,
            resumo_fatos=resumo, embeddings_chunks=vetores,
        )
        salva = await self._rag_repo.salvar(fonte)
        await self._sincronizar_brand_bible(conta)
        return salva

    async def _indexar_extraido(
        self, empresa_id: UUID, conta_ig_id: UUID, tipo: TipoFonteRAG,
        titulo_custom: str, titulo_padrao: str, texto: str,
    ) -> FonteRAG:
        cmd = IndexarFonteRagCmd(
            empresa_id=empresa_id, conta_ig_id=conta_ig_id, tipo=tipo,
            titulo=(titulo_custom.strip() or titulo_padrao)[:240], conteudo=texto,
        )
        return await self.indexar_fonte(cmd)

    async def indexar_arquivo(self, cmd: IndexarArquivoRagCmd) -> FonteRAG:
        """Extrai texto de arquivo (.pdf, .txt, .md) e indexa na base RAG da conta."""
        if self._extrator is None:
            raise ErroValidacaoDominio("Extrator de arquivos RAG não configurado.")
        nome, texto = self._extrator.extrair_arquivo(cmd.nome_arquivo, cmd.conteudo_bytes)
        return await self._indexar_extraido(
            cmd.empresa_id, cmd.conta_ig_id, cmd.tipo, cmd.titulo, nome, texto
        )

    async def indexar_url(self, cmd: IndexarUrlRagCmd) -> FonteRAG:
        """Extrai página web pública anti-SSRF e indexa no RAG da conta."""
        if self._extrator is None:
            raise ErroValidacaoDominio("Extrator de URLs RAG não configurado.")
        titulo_pag, texto = await self._extrator.extrair_url(cmd.url)
        return await self._indexar_extraido(
            cmd.empresa_id, cmd.conta_ig_id, cmd.tipo, cmd.titulo, titulo_pag, texto
        )

    async def listar_fontes(self, empresa_id: UUID, conta_ig_id: UUID) -> list[FonteRAG]:
        await self.exigir_conta(empresa_id, conta_ig_id)
        return await self._rag_repo.listar_por_conta(empresa_id, conta_ig_id)

    async def remover_fonte(self, empresa_id: UUID, conta_ig_id: UUID, fonte_id: UUID) -> bool:
        conta = await self.exigir_conta(empresa_id, conta_ig_id)
        removida = await self._rag_repo.remover(empresa_id, conta_ig_id, fonte_id)
        if removida:
            await self._sincronizar_brand_bible(conta)
        return removida

    async def recuperar_contexto(
        self, empresa_id: UUID, conta_ig_id: UUID, consulta: str,
        top_k: int = 4, max_chars: int = 1800,
    ) -> list[str]:
        """Seleciona os chunks mais relevantes via busca híbrida (lexical + cosseno)."""
        fontes = await self._rag_repo.listar_por_conta(empresa_id, conta_ig_id)
        q = consulta.strip()
        if not fontes or not q:
            return []
        emb_consulta: list[float] | None = None
        if self._embeddings is not None and any(f.embeddings_chunks for f in fontes):
            vetores = await self._gerar_embeddings_seguro(empresa_id, conta_ig_id, [q])
            emb_consulta = vetores[0] if vetores else None
        return ranquear_trechos_rag(fontes, consulta, emb_consulta, top_k, max_chars)

    @staticmethod
    def montar_system_prompt(conta: ContaInstagram, config: ConfigIAConta) -> str:
        """Constrói prompt de sistema cacheável com Brand Bible e templates da conta."""
        return montar_system_prompt_com_brand_bible(conta, config)

    @staticmethod
    def formatar_ancoras_visuais(midias: list[MidiaBiblioteca], limite: int = 4) -> str:
        """Prioriza mídias curtidas (curtida_favorita=True) como referência estética."""
        return formatar_ancoras_visuais_lista(midias, limite)
