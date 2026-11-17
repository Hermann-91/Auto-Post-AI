"""Helpers puros de formatação e normalização de itens do Planejamento Semanal."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any
from uuid import UUID

from app.aplicacao.ia.dtos import CriarConteudoCmd, ProporPlanejamentoCmd
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoMidia


def normalizar_formato_midia(valor: Any) -> TipoMidia:
    """Converte texto livre da IA para TipoMidia suportado (padrão IMAGE)."""
    bruto = str(valor or "IMAGE").strip().upper()
    try:
        return TipoMidia(bruto)
    except ValueError:
        return TipoMidia.IMAGE


def normalizar_itens_grade(
    itens_brutos: list[Any],
    quantidade: int,
    incluir_imagens_ia: bool,
    formatos_esperados: list[TipoMidia] | None = None,
) -> list[dict[str, Any]]:
    """Valida e normaliza os itens retornados pela IA na Etapa 1 da semana."""
    filtrados = [i for i in itens_brutos if isinstance(i, dict)]
    if not filtrados:
        raise ErroValidacaoDominio("A IA não retornou itens válidos para a grade semanal.")
    normalizados: list[dict[str, Any]] = []
    for idx in range(1, quantidade + 1):
        item = filtrados[idx - 1] if (idx - 1) < len(filtrados) else {}
        formato = (
            formatos_esperados[idx - 1]
            if formatos_esperados and (idx - 1) < len(formatos_esperados)
            else normalizar_formato_midia(item.get("formato"))
        )
        usar_img = (
            incluir_imagens_ia
            and formato != TipoMidia.REELS
            and bool(item.get("usar_ia_imagem", True))
        )
        normalizados.append(
            {
                "ordem": idx,
                "dia_semana": str(item.get("dia_semana") or f"Dia {idx}"),
                "horario_sugerido": str(item.get("horario_sugerido") or "18:00"),
                "formato": formato.value,
                "tema": str(item.get("tema") or f"Pauta {idx}"),
                "objetivo": str(item.get("objetivo") or "engajamento"),
                "gancho": str(item.get("gancho") or ""),
                "ideia_visual": str(item.get("ideia_visual") or ""),
                "usar_ia_imagem": usar_img,
                "legenda_previa": str(item.get("legenda_previa") or ""),
                "editar_midia_id": (
                    str(item["editar_midia_id"]) if item.get("editar_midia_id") else None
                ),
                "midia_base_ids": [str(m) for m in (item.get("midia_base_ids") or [])],
                "presets_melhoria": [str(p) for p in (item.get("presets_melhoria") or [])],
            }
        )
    return normalizados


def montar_prompt_grade_semanal(
    cmd: ProporPlanejamentoCmd,
    nicho: str,
    regiao: str,
    tendencias: dict[str, Any],
    chunks: list[str],
    ancoras: str,
    formatos_esperados: list[TipoMidia] | None = None,
) -> str:
    """Monta prompt de usuário estruturado combinando tendências, RAG e referências."""
    topicos_txt = "; ".join(
        f"{t.get('titulo', '')}: {t.get('resumo', '')}"
        for t in (tendencias.get("topicos") or [])[:4]
    )
    bloco_rag = "\n".join(chunks) if chunks else "Nenhuma"
    bloco_comp = ""
    if formatos_esperados:
        cont = Counter(f.value for f in formatos_esperados)
        resumo_comp = ", ".join(f"{qtd} {fmt}" for fmt, qtd in cont.items())
        bloco_comp = f"\nDistribuição obrigatória de formatos: {resumo_comp}."
    total_posts = len(formatos_esperados) if formatos_esperados else cmd.quantidade_posts
    return (
        f"Planeje {total_posts} postagens para a semana de {cmd.semana_inicio}.{bloco_comp}\n"
        f"Objetivo: {cmd.objetivo_semana}\n"
        f"Tendências atuais ({nicho}/{regiao}): {topicos_txt}\n"
        f"Base RAG:\n{bloco_rag}\n"
        f"Referências visuais favoritas:\n{ancoras}\n"
        'Retorne JSON com chave "itens": lista de objetos contendo '
        '"dia_semana", "horario_sugerido", "formato" (IMAGE/CAROUSEL/REELS/STORIES), '
        '"tema", "objetivo", "gancho", "ideia_visual", "usar_ia_imagem" (bool).'
    )


def montar_cmd_item_grade(
    empresa_id: UUID,
    conta_ig_id: UUID,
    plano_id: UUID,
    item: dict[str, Any],
    agendar_para: datetime | None = None,
) -> CriarConteudoCmd:
    """Converte um item da grade semanal em comando de criação individual."""
    formato_orig = normalizar_formato_midia(item.get("formato"))
    gerar_img = bool(item.get("usar_ia_imagem", False))
    editar_id_str = item.get("editar_midia_id")
    editar_midia_id = UUID(str(editar_id_str)) if editar_id_str else None
    midia_base_ids = tuple(UUID(str(m)) for m in (item.get("midia_base_ids") or []) if m)
    presets = tuple(str(p) for p in (item.get("presets_melhoria") or []) if str(p).strip())
    legenda_previa = str(item.get("legenda_previa") or "").strip()
    formato_efetivo = (
        TipoMidia.STORIES
        if formato_orig == TipoMidia.STORIES
        else (TipoMidia.IMAGE if (gerar_img or editar_midia_id is not None) else formato_orig)
    )
    dia = str(item.get("dia_semana") or "").strip()
    tema_base = str(item.get("tema") or "Conteúdo semanal").strip()
    tom_extra = f"Use como base esta legenda aprovada: {legenda_previa}" if legenda_previa else ""
    return CriarConteudoCmd(
        empresa_id=empresa_id,
        conta_ig_id=conta_ig_id,
        tipo_midia=formato_efetivo,
        tema=f"[{dia} • {formato_orig.value}] {tema_base}" if dia else tema_base,
        objetivo=str(item.get("objetivo") or "engajamento"),
        tom_extra=tom_extra,
        gerar_imagem_ia=gerar_img,
        editar_midia_id=editar_midia_id,
        midia_base_ids=midia_base_ids,
        prompt_visual_extra=str(item.get("ideia_visual") or ""),
        presets_melhoria=presets,
        proporcao="9:16" if formato_efetivo == TipoMidia.STORIES else "4:5",
        salvar_rascunho=True,
        planejamento_id=plano_id,
        agendar_para=agendar_para,
    )
