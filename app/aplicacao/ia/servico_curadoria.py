"""Curadoria visual econômica de mídias da biblioteca via OpenRouter Visão."""

from __future__ import annotations

import base64
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from app.aplicacao.ia.dtos import CompactadorMiniaturaPort, CuradoriaVisualDTO
from app.aplicacao.ia.json_ia import extrair_objeto_json
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.aplicacao.ia.servico_prompts_rag import ServicoPromptsRagUseCase
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.portas.ia_meta import ClienteVisaoMultimodalPort, ClienteVisaoPort
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort


@dataclass(frozen=True, slots=True)
class CuradoriaLoteDTO:
    """Resultado da curadoria comparativa entre até 5 fotos da conta."""

    midia_vencedora: MidiaBiblioteca
    indice_vencedora: int
    justificativa: str
    avaliacoes: list[dict[str, Any]]
    custo_usd: Decimal
    modelo_usado: str


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

    async def eleger_melhor_foto(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        midia_ids: Sequence[UUID],
        objetivo_contexto: str = "",
        modelo_visao: str | None = None,
    ) -> CuradoriaLoteDTO:
        """Analisa até 5 imagens da conta e elege a foto mais forte para o objetivo."""
        conta = await self._prompts_rag.exigir_conta(empresa_id, conta_ig_id)
        unicas = list(dict.fromkeys(midia_ids))
        if not 1 <= len(unicas) <= 5:
            raise ErroValidacaoDominio("Curadoria comparativa exige entre 1 e 5 fotos da conta.")

        midias: list[MidiaBiblioteca] = []
        for midia_id in unicas:
            m = await self._midia_repo.buscar_por_id(empresa_id, conta_ig_id, midia_id)
            if m is None:
                raise ErroValidacaoDominio("Uma das mídias informadas não pertence a esta conta.")
            if not m.tipo_arquivo.startswith("image/"):
                raise ErroValidacaoDominio("Curadoria comparativa suporta apenas imagens.")
            midias.append(m)

        if len(midias) == 1:
            res_unica = await self.curar_midia(
                empresa_id, conta_ig_id, midias[0].id, modelo_visao=modelo_visao
            )
            return CuradoriaLoteDTO(
                midia_vencedora=res_unica.midia, indice_vencedora=1,
                justificativa=res_unica.resumo_visual, avaliacoes=[],
                custo_usd=res_unica.custo_usd, modelo_usado=res_unica.modelo_usado,
            )

        modelo_alvo = (modelo_visao or self._modelo_visao).strip()
        decisao = await self._orcamento.decidir_politica_chamada(
            empresa_id, modelo_alvo, estimar_chamada(modelo_alvo, eh_imagem=False), False
        )
        data_urls: list[str] = []
        for m in midias:
            bruto = await self._storage.baixar_bytes(m.chave_storage)
            mini = self._compactar(bruto, max_lado=768, qualidade=75)
            data_urls.append(f"data:image/jpeg;base64,{base64.b64encode(mini).decode('ascii')}")

        sys_p = f"Diretor de arte do Instagram @{conta.username}. Retorne apenas JSON válido."
        obj_txt = f" Objetivo: {objetivo_contexto.strip()}." if objetivo_contexto.strip() else ""
        usr_p = (
            f"Compare as {len(midias)} fotos enviadas em ordem (1 a {len(midias)}).{obj_txt}\n"
            "Avalie nitidez, iluminação, composição e potencial de engajamento.\n"
            'Retorne JSON: {"indice_vencedora": 1, "justificativa": "...", '
            '"avaliacoes": [{"indice": 1, "nota": 9, "destaque": "..."}]}'
        )
        if hasattr(self._visao, "analisar_multiplas_imagens"):
            cliente_multi = cast(ClienteVisaoMultimodalPort, self._visao)
            bruto_txt, usage = await cliente_multi.analisar_multiplas_imagens(
                sys_p, usr_p, data_urls, decisao.modelo_efetivo
            )
        else:
            bruto_txt, usage = await self._visao.analisar_imagem(
                sys_p, usr_p, data_urls[0], decisao.modelo_efetivo
            )
        reg = await self._orcamento.registrar_consumo(empresa_id, conta_ig_id, usage)

        indice, justificativa, avaliacoes = 1, bruto_txt.strip()[:400], []
        try:
            obj = extrair_objeto_json(bruto_txt)
            indice = max(1, min(int(obj.get("indice_vencedora") or 1), len(midias)))
            justificativa = str(obj.get("justificativa") or justificativa).strip()
            if isinstance(obj.get("avaliacoes"), list):
                avaliacoes = [a for a in obj["avaliacoes"] if isinstance(a, dict)]
        except (ErroValidacaoDominio, TypeError, ValueError):
            pass

        return CuradoriaLoteDTO(
            midia_vencedora=midias[indice - 1],
            indice_vencedora=indice,
            justificativa=justificativa,
            avaliacoes=avaliacoes,
            custo_usd=reg.custo_usd,
            modelo_usado=reg.modelo,
        )
