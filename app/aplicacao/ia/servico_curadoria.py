"""Curadoria visual econômica de mídias da biblioteca via OpenRouter Visão."""

from __future__ import annotations

import base64
from uuid import UUID

from app.aplicacao.ia.dtos import CompactadorMiniaturaPort, CuradoriaVisualDTO
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.portas.ia_meta import ClienteVisaoPort
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort


class ServicoCuradoriaVisualUseCase:
    """Gera descrição visual curta com miniatura <= 1024px para uso como âncora."""

    def __init__(
        self,
        midia_repo: MidiaRepositoryPort,
        storage: StorageMidiaPort,
        cliente_visao: ClienteVisaoPort,
        orcamento: ServicoOrcamentoUseCase,
        prompts_rag: ServicoPromptsRagUseCase,
        compactador: CompactadorMiniaturaPort,
        modelo_visao_padrao: str = "google/gemini-2.5-flash-lite",
    ) -> None:
        self._midia_repo = midia_repo
        self._storage = storage
        self._visao = cliente_visao
        self._orcamento = orcamento
        self._prompts_rag = prompts_rag
        self._compactar = compactador
        self._modelo_visao = modelo_visao_padrao

    async def curar_midia(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        midia_id: UUID,
        modelo_visao: str | None = None,
    ) -> CuradoriaVisualDTO:
        """Compacta miniatura <= 1024px, analisa via IA e salva resumo_visual."""
        conta = await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        midia = await self._midia_repo.buscar_por_id(empresa_id, conta_ig_id, midia_id)
        if midia is None:
            raise ErroValidacaoDominio("Mídia não encontrada para curadoria.")
        if not midia.tipo_arquivo.startswith("image/"):
            raise ErroValidacaoDominio("Curadoria visual suporta apenas arquivos de imagem.")

        modelo_alvo = (modelo_visao or self._modelo_visao).strip()
        decisao = await self._orcamento.decidir_politica_chamada(
            empresa_id=empresa_id,
            modelo_desejado=modelo_alvo,
            custo_estimado=estimar_chamada(modelo_alvo, eh_imagem=False),
            exige_imagem_paga=False,
        )

        bruto = await self._storage.baixar_bytes(midia.chave_storage)
        miniatura = self._compactar(bruto, max_lado=1024, qualidade=80)
        b64 = base64.b64encode(miniatura).decode("ascii")
        data_url = f"data:image/jpeg;base64,{b64}"

        system_prompt = (
            f"Descreva imagens para planejamento de conteúdo do Instagram @{conta.username}."
        )
        user_prompt = (
            "Resuma em no máximo 2 frases curtas (até 220 caracteres) o assunto principal, "
            "enquadramento, iluminação e estilo estético desta foto."
        )
        resumo, usage = await self._visao.analisar_imagem(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            imagem_data_url=data_url,
            modelo=decisao.modelo_efetivo,
        )
        registro = await self._orcamento.registrar_consumo(empresa_id, conta_ig_id, usage)

        midia.resumo_visual = resumo.strip()[:400]
        salva = await self._midia_repo.salvar(midia)
        return CuradoriaVisualDTO(
            midia=salva,
            resumo_visual=salva.resumo_visual,
            custo_usd=registro.custo_usd,
            modelo_usado=registro.modelo,
        )
