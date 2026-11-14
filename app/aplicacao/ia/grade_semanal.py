"""Helpers puros de formatação e normalização de itens do Planejamento Semanal."""

from __future__ import annotations

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
) -> list[dict[str, Any]]:
    """Valida e normaliza os itens retornados pela IA na Etapa 1 da semana."""
    normalizados: list[dict[str, Any]] = []
    for idx, item in enumerate(itens_brutos[:quantidade], start=1):
        if not isinstance(item, dict):
            continue
        formato = normalizar_formato_midia(item.get("formato"))
        usar_img = incluir_imagens_ia and bool(item.get("usar_ia_imagem", True))
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
            }
        )
    if not normalizados:
        raise ErroValidacaoDominio("A IA não retornou itens válidos para a grade semanal.")
    return normalizados


def montar_prompt_grade_semanal(
    cmd: ProporPlanejamentoCmd,
    nicho: str,
    regiao: str,
    tendencias: dict[str, Any],
    chunks: list[str],
    ancoras: str,
) -> str:
    """Monta prompt de usuário estruturado combinando tendências, RAG e referências."""
    topicos_txt = "; ".join(
        f"{t.get('titulo', '')}: {t.get('resumo', '')}"
        for t in (tendencias.get("topicos") or [])[:4]
    )
    bloco_rag = "\n".join(chunks) if chunks else "Nenhuma"
    return (
        f"Planeje {cmd.quantidade_posts} postagens para a semana de {cmd.semana_inicio}.\n"
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
) -> CriarConteudoCmd:
    """Converte um item da grade semanal em comando de criação individual."""
    formato_orig = normalizar_formato_midia(item.get("formato"))
    gerar_img = bool(item.get("usar_ia_imagem", False))
    formato_efetivo = (
        TipoMidia.STORIES
        if formato_orig == TipoMidia.STORIES
        else (TipoMidia.IMAGE if gerar_img else formato_orig)
    )
    dia = str(item.get("dia_semana") or "").strip()
    tema_base = str(item.get("tema") or "Conteúdo semanal").strip()
    return CriarConteudoCmd(
        empresa_id=empresa_id,
        conta_ig_id=conta_ig_id,
        tipo_midia=formato_efetivo,
        tema=f"[{dia} • {formato_orig.value}] {tema_base}" if dia else tema_base,
        objetivo=str(item.get("objetivo") or "engajamento"),
        gerar_imagem_ia=gerar_img,
        prompt_visual_extra=str(item.get("ideia_visual") or ""),
        proporcao="9:16" if formato_efetivo == TipoMidia.STORIES else "4:5",
        salvar_rascunho=gerar_img,
        planejamento_id=plano_id,
    )
