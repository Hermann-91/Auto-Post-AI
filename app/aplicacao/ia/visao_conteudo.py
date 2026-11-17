"""Análise visual de fotos anexadas (miniatura <= 1024px) e montagem do prompt Copywriter."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.aplicacao.ia.dtos import CompactadorMiniaturaPort, CriarConteudoCmd
from app.aplicacao.ia.json_ia import extrair_objeto_json
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroIntegracaoIA, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import TipoMidia
from app.dominio.portas.ia_meta import ClienteIAPort, ClienteVisaoPort
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort


@dataclass(frozen=True, slots=True)
class ResumoVisaoAnexadaDTO:
    """Resultado da análise visual de uma mídia real anexada ao post."""

    descricao_visual: str
    horario_sugerido: str
    justificativa_horario: str
    custo_usd: Decimal
    modelo_usado: str


async def analisar_fotos_anexadas(
    conta: ContaInstagram,
    bases: list[MidiaBiblioteca],
    visao: ClienteVisaoPort,
    storage: StorageMidiaPort,
    compactar: CompactadorMiniaturaPort,
    orcamento: ServicoOrcamentoUseCase,
    midia_repo: MidiaRepositoryPort,
    modelo_visao: str,
) -> ResumoVisaoAnexadaDTO | None:
    """Compacta miniatura da foto anexada e obtém descrição visual + sugestão de horário."""
    imagens = [m for m in bases if m.tipo_arquivo.startswith("image/")]
    if not imagens:
        return None
    alvo = imagens[0]
    modelo = modelo_visao.strip() or "google/gemini-2.5-flash-lite"
    decisao = await orcamento.decidir_politica_chamada(
        empresa_id=conta.empresa_id,
        modelo_desejado=modelo,
        custo_estimado=estimar_chamada(modelo, eh_imagem=False),
        exige_imagem_paga=False,
    )
    bruto = await storage.baixar_bytes(alvo.chave_storage)
    miniatura = compactar(bruto, max_lado=1024, qualidade=80)
    data_url = f"data:image/jpeg;base64,{base64.b64encode(miniatura).decode('ascii')}"

    sys_prompt = (
        f"Você analisa fotos reais para o Instagram @{conta.username}. "
        "Retorne apenas JSON válido."
    )
    usr_prompt = (
        "Descreva objetivamente o que aparece na foto real anexada e recomende o melhor "
        "horário estratégico de postagem no Instagram.\n"
        'JSON esperado: {"descricao_visual": "...", "horario_sugerido": "HH:MM", '
        '"justificativa_horario": "..."}'
    )
    resposta, usage = await visao.analisar_imagem(
        system_prompt=sys_prompt,
        user_prompt=usr_prompt,
        imagem_data_url=data_url,
        modelo=decisao.modelo_efetivo,
    )
    reg = await orcamento.registrar_consumo(conta.empresa_id, conta.id, usage)

    descricao = resposta.strip()
    horario = "18:00"
    justificativa = ""
    try:
        obj = extrair_objeto_json(resposta)
        descricao = str(obj.get("descricao_visual") or "").strip() or descricao
        horario = str(obj.get("horario_sugerido") or "18:00").strip()[:10]
        justificativa = str(obj.get("justificativa_horario") or "").strip()
    except ErroValidacaoDominio:
        pass

    if not alvo.resumo_visual.strip() and descricao:
        alvo.resumo_visual = descricao[:400]
        await midia_repo.salvar(alvo)

    return ResumoVisaoAnexadaDTO(
        descricao_visual=descricao,
        horario_sugerido=horario,
        justificativa_horario=justificativa,
        custo_usd=reg.custo_usd,
        modelo_usado=reg.modelo,
    )


def montar_prompt_copywriter(
    cmd: CriarConteudoCmd,
    rag_bloco: str,
    ancoras_visuais: str | None,
    visao_anexada: ResumoVisaoAnexadaDTO | None,
) -> str:
    """Constrói prompt estruturado do Copywriter combinando RAG, série e visão real."""
    bloco_pilar = f" | Pilar: {cmd.pilar_editorial}" if cmd.pilar_editorial.strip() else ""
    bloco_serie = (
        f"\nSérie narrativa ativa (etapa: {cmd.etapa_serie or 'sequencial'})."
        if cmd.modo_serie
        else ""
    )
    bloco_visao = ""
    if visao_anexada is not None:
        bloco_visao = (
            f"\nAnálise visual da foto anexada: {visao_anexada.descricao_visual}"
            f"\nHorário estratégico sugerido: {visao_anexada.horario_sugerido}"
        )
    base = (
        f"Formato: {cmd.tipo_midia.value} | Tema: {cmd.tema} | "
        f"Objetivo: {cmd.objetivo}{bloco_pilar}\n"
        f"Instrução extra de tom: {cmd.tom_extra or 'padrão da conta'}{bloco_serie}{bloco_visao}\n"
        f"Base de conhecimento:\n{rag_bloco}\n"
    )
    regras_json = (
        'Retorne JSON com chaves: "legenda" (string vazia ""), '
        '"hashtags" (lista vazia []), "roteiro_slides" (lista de textos curtos para tela).'
        if cmd.tipo_midia == TipoMidia.STORIES
        else 'Retorne JSON válido com chaves OBRIGATÓRIAS: "legenda" (texto completo e '
        'envolvente em PT-BR, NUNCA vazio), "hashtags" (3 a 6 strings), '
        '"roteiro_slides" (lista de slides se CAROUSEL).'
    )
    if ancoras_visuais is None:
        return f"{base}{regras_json}"
    return (
        f"{base}Memória visual da conta:\n{ancoras_visuais}\n"
        f'{regras_json} Inclua também "prompt_visual" (descrição fotográfica direta).'
    )


def _extrair_campos_copy(
    dados: dict[str, Any], tipo_midia: TipoMidia
) -> tuple[str, list[str], list[str], str]:
    eh_stories = tipo_midia == TipoMidia.STORIES
    bruto_tags, bruto_rot = dados.get("hashtags"), dados.get("roteiro_slides")
    hashtags = (
        [str(h) for h in bruto_tags if str(h).strip()] if isinstance(bruto_tags, list) else []
    )
    roteiro = (
        [str(s) for s in bruto_rot if str(s).strip()] if isinstance(bruto_rot, list) else []
    )
    chaves = ("legenda", "caption", "texto", "copy")
    bruto_leg = next(
        (str(dados.get(k) or "").strip() for k in chaves if str(dados.get(k) or "").strip()), ""
    )
    if not bruto_leg and not eh_stories and roteiro:
        bruto_leg = "\n".join(roteiro)
    legenda = "" if eh_stories else bruto_leg
    return legenda, hashtags, roteiro, str(dados.get("prompt_visual") or "").strip()


async def gerar_copy_validada(
    cliente_ia: ClienteIAPort,
    orcamento: ServicoOrcamentoUseCase,
    cmd: CriarConteudoCmd,
    system_prompt: str,
    user_prompt: str,
    modelo_efetivo: str,
) -> tuple[str, list[str], list[str], str, Decimal, list[str]]:
    """Executa Copywriter com 1 retry automático caso legenda venha vazia fora de STORIES."""
    custo_txt, modelos, prompt_atual = Decimal("0"), [], user_prompt
    for tentativa in range(2):
        bruto, usage = await cliente_ia.gerar_texto(
            system_prompt, prompt_atual, modelo_efetivo, formato_json=True
        )
        reg = await orcamento.registrar_consumo(cmd.empresa_id, cmd.conta_ig_id, usage)
        custo_txt += reg.custo_usd
        modelos.append(reg.modelo)
        legenda, hashtags, roteiro, prompt_vis = _extrair_campos_copy(
            extrair_objeto_json(bruto), cmd.tipo_midia
        )
        if cmd.tipo_midia == TipoMidia.STORIES or legenda:
            return legenda, hashtags, roteiro, prompt_vis, custo_txt, modelos
        if tentativa == 0:
            await orcamento.decidir_politica_chamada(
                cmd.empresa_id, modelo_efetivo, estimar_chamada(modelo_efetivo), False
            )
            prompt_atual = (
                f"{user_prompt}\n\nATENÇÃO: na resposta anterior o campo 'legenda' veio vazio. "
                f"Escreva uma legenda completa em PT-BR para {cmd.tipo_midia.value}."
            )
    raise ErroIntegracaoIA("A IA retornou legenda vazia. Tente informar um tema mais específico.")
