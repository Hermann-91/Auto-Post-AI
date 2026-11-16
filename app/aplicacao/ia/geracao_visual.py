"""Auxiliar de geração/edição Nano Banana com pipeline determinístico $0."""

from __future__ import annotations

import base64
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.aplicacao.ia.dtos import (
    CompactadorMiniaturaPort,
    CriarConteudoCmd,
    PipelineMidiaPort,
)
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.dominio.entidades.ia_rag import ConfigIAConta
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, TipoMidia
from app.dominio.portas.ia_meta import ClienteIAPort
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort
from app.infra.midia.processador_imagem import (
    ProcessadorImagem,
    abrir_imagem_segura,
    serializar_jpeg,
)

MAPA_PROMPT_PRESETS: dict[str, str] = {
    "fullhd": "ultra high resolution, 8k fullhd, crisp optical sharpness, fine micro-texture",
    "foto_profissional": "professional studio photography, DSLR 85mm lens, commercial grade",
    "iluminacao": "balanced HDR studio lighting, soft natural highlights, rich dynamic range",
}


class GeradorVisualHibrido:
    """Executa estágio pago opcional (Nano Banana) + pós-processamento obrigatório ($0)."""

    def __init__(
        self,
        midia_repo: MidiaRepositoryPort,
        storage: StorageMidiaPort,
        cliente_ia: ClienteIAPort,
        orcamento: ServicoOrcamentoUseCase,
        pipeline_midia: PipelineMidiaPort,
        compactador: CompactadorMiniaturaPort,
        cota_midia: CotaMidia | None = None,
    ) -> None:
        self._midia_repo = midia_repo
        self._storage = storage
        self._ia = cliente_ia
        self._orcamento = orcamento
        self._pipeline = pipeline_midia
        self._compactar = compactador
        self._cota = cota_midia or CotaMidia()

    async def gerar_e_persistir(
        self,
        cmd: CriarConteudoCmd,
        config: ConfigIAConta,
        prompt_visual: str,
    ) -> tuple[MidiaBiblioteca, Decimal, str]:
        """Gera/edita imagem, enquadra no padrão Meta e salva em IA-Cria ou IA-Edita."""
        modelo_img = (cmd.modelo_imagem or config.modelo_img_pref).strip()
        decisao = await self._orcamento.decidir_politica_chamada(
            cmd.empresa_id,
            modelo_img,
            estimar_chamada(modelo_img, eh_imagem=True),
            exige_imagem_paga=True,
        )

        imagem_base_url, pasta_destino = await self._preparar_imagem_base(cmd)
        tags_presets = [
            MAPA_PROMPT_PRESETS[p.lower()]
            for p in cmd.presets_melhoria
            if p.lower() in MAPA_PROMPT_PRESETS
        ]
        sufixo_presets = ", ".join(tags_presets)
        prompt_final = ". ".join(
            parte
            for parte in (prompt_visual, cmd.prompt_visual_extra, sufixo_presets)
            if parte.strip()
        ).strip(" .")
        img_ia_bytes, usage = await self._ia.gerar_ou_editar_imagem(
            prompt=prompt_final,
            modelo=decisao.modelo_efetivo,
            imagem_base_url=imagem_base_url,
        )
        reg = await self._orcamento.registrar_consumo(cmd.empresa_id, cmd.conta_ig_id, usage)

        tipo_pipe = TipoMidia.IMAGE if cmd.tipo_midia == TipoMidia.CAROUSEL else cmd.tipo_midia
        proporcao = "9:16" if tipo_pipe == TipoMidia.STORIES else cmd.proporcao
        aplicar_logo = (
            config.aplicar_logo_padrao if cmd.aplicar_logo is None else cmd.aplicar_logo
        )
        params: dict[str, Any] = {
            "proporcao": proporcao,
            "aplicar_logo": aplicar_logo and cmd.logo_bytes is not None,
            "logo_bytes": cmd.logo_bytes,
            "eh_video": False,
        }
        jpeg_final = (await self._pipeline.processar(tipo_pipe, [img_ia_bytes], params))[0]
        if cmd.presets_melhoria:
            img_tratada = ProcessadorImagem.aplicar_presets_melhoria(
                abrir_imagem_segura(jpeg_final), cmd.presets_melhoria
            )
            jpeg_final = serializar_jpeg(img_tratada, qualidade=95)

        qtd, bytes_usados = await self._midia_repo.calcular_uso_cota(
            cmd.empresa_id, cmd.conta_ig_id
        )
        self._cota.validar_novo_arquivo(qtd, bytes_usados, len(jpeg_final))
        chave = MidiaBiblioteca.montar_chave_storage(
            cmd.empresa_id, cmd.conta_ig_id, pasta_destino, f"ia_{uuid4().hex[:12]}.jpg"
        )
        await self._storage.enviar_bytes(chave, jpeg_final, "image/jpeg")
        midia = MidiaBiblioteca(
            empresa_id=cmd.empresa_id,
            conta_ig_id=cmd.conta_ig_id,
            pasta=pasta_destino,
            chave_storage=chave,
            tipo_arquivo="image/jpeg",
            tamanho_bytes=len(jpeg_final),
            resumo_visual=prompt_final[:300],
        )
        try:
            salva = await self._midia_repo.salvar(midia)
        except Exception:
            await self._storage.remover_objeto(chave)
            raise
        return salva, reg.custo_usd, reg.modelo

    async def _preparar_imagem_base(self, cmd: CriarConteudoCmd) -> tuple[str | None, PastaMidia]:
        if cmd.editar_midia_id is None:
            return None, PastaMidia.IA_CRIA
        origem = await self._midia_repo.buscar_por_id(
            cmd.empresa_id, cmd.conta_ig_id, cmd.editar_midia_id
        )
        if origem is None:
            raise ErroValidacaoDominio("Mídia para edição não encontrada nesta conta.")
        bruto = await self._storage.baixar_bytes(origem.chave_storage)
        mini = self._compactar(bruto, max_lado=1024, qualidade=85)
        data_url = f"data:image/jpeg;base64,{base64.b64encode(mini).decode('ascii')}"
        return data_url, PastaMidia.IA_EDITA
