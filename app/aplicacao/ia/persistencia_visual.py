"""Helpers de I/O de referências reais e pós-processamento Pillow ($0) do pipeline visual."""

from __future__ import annotations

import base64
from typing import Any
from uuid import uuid4

from app.aplicacao.ia.dtos import (
    CompactadorMiniaturaPort,
    CriarConteudoCmd,
    PipelineMidiaPort,
)
from app.dominio.entidades.ia_rag import ConfigIAConta
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.dominio.objetos_valor.enums_conteudo import PastaMidia, TipoMidia
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort
from app.infra.midia.processador_imagem import (
    ProcessadorImagem,
    abrir_imagem_segura,
    serializar_jpeg,
)


async def preparar_referencias_visuais_conta(
    midia_repo: MidiaRepositoryPort,
    storage: StorageMidiaPort,
    compactar: CompactadorMiniaturaPort,
    cmd: CriarConteudoCmd,
) -> tuple[list[str], PastaMidia]:
    """Carrega e compacta mídias de referência pertencentes à conta ativa."""
    pasta = PastaMidia.IA_EDITA if cmd.editar_midia_id is not None else PastaMidia.IA_CRIA
    ids_brutos = ([cmd.editar_midia_id] if cmd.editar_midia_id is not None else []) + list(
        cmd.midia_base_ids
    )
    urls: list[str] = []
    for midia_id in dict.fromkeys(ids_brutos):
        origem = await midia_repo.buscar_por_id(cmd.empresa_id, cmd.conta_ig_id, midia_id)
        if origem is None:
            raise ErroValidacaoDominio("Mídia de referência não encontrada nesta conta.")
        bruto = await storage.baixar_bytes(origem.chave_storage)
        mini = compactar(bruto, max_lado=1024, qualidade=85)
        urls.append(f"data:image/jpeg;base64,{base64.b64encode(mini).decode('ascii')}")
    return urls, pasta


async def pos_processar_e_salvar_midia(
    midia_repo: MidiaRepositoryPort,
    storage: StorageMidiaPort,
    pipeline: PipelineMidiaPort,
    cota: CotaMidia,
    cmd: CriarConteudoCmd,
    config: ConfigIAConta,
    img_ia_bytes: bytes,
    pasta_destino: PastaMidia,
    resumo_visual: str,
) -> MidiaBiblioteca:
    """Aplica enquadramento Meta ($0), presets, cota e salva no storage com rollback."""
    tipo_pipe = TipoMidia.IMAGE if cmd.tipo_midia == TipoMidia.CAROUSEL else cmd.tipo_midia
    proporcao = "9:16" if tipo_pipe == TipoMidia.STORIES else cmd.proporcao
    aplicar_logo = config.aplicar_logo_padrao if cmd.aplicar_logo is None else cmd.aplicar_logo
    params: dict[str, Any] = {
        "proporcao": proporcao,
        "logo_bytes": cmd.logo_bytes,
        "eh_video": False,
        "aplicar_logo": aplicar_logo and cmd.logo_bytes is not None,
    }
    jpeg_final = (await pipeline.processar(tipo_pipe, [img_ia_bytes], params))[0]
    if cmd.presets_melhoria:
        img_tratada = ProcessadorImagem.aplicar_presets_melhoria(
            abrir_imagem_segura(jpeg_final), cmd.presets_melhoria
        )
        jpeg_final = serializar_jpeg(img_tratada, qualidade=95)
    qtd, bytes_usados = await midia_repo.calcular_uso_cota(cmd.empresa_id, cmd.conta_ig_id)
    cota.validar_novo_arquivo(qtd, bytes_usados, len(jpeg_final))
    chave = MidiaBiblioteca.montar_chave_storage(
        cmd.empresa_id, cmd.conta_ig_id, pasta_destino, f"ia_{uuid4().hex[:12]}.jpg"
    )
    await storage.enviar_bytes(chave, jpeg_final, "image/jpeg")
    midia = MidiaBiblioteca(
        empresa_id=cmd.empresa_id,
        conta_ig_id=cmd.conta_ig_id,
        pasta=pasta_destino,
        chave_storage=chave,
        tipo_arquivo="image/jpeg",
        tamanho_bytes=len(jpeg_final),
        resumo_visual=resumo_visual,
    )
    try:
        return await midia_repo.salvar(midia)
    except Exception:
        await storage.remover_objeto(chave)
        raise
