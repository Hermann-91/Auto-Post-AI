"""Análise visual de fotos anexadas (miniatura <= 1024px) e montagem do prompt Copywriter."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import Decimal

from app.aplicacao.ia.dtos import CompactadorMiniaturaPort, CriarConteudoCmd
from app.aplicacao.ia.json_ia import extrair_objeto_json
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.portas.ia_meta import ClienteVisaoPort
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
    if ancoras_visuais is None:
        return (
            f"{base}"
            'Retorne JSON com chaves: "legenda" (string vazia se STORIES), '
            '"hashtags" (lista de strings), "roteiro_slides" (lista de strings).'
        )
    return (
        f"{base}Memória visual da conta:\n{ancoras_visuais}\n"
        'Retorne JSON com chaves: "legenda" (string vazia se STORIES), '
        '"hashtags" (lista de strings), "prompt_visual" (string descritiva), '
        '"roteiro_slides" (lista de strings).'
    )
