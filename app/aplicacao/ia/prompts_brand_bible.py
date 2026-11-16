"""Compilação determinística de Brand Bible e ativação de templates no system prompt."""

from __future__ import annotations

import json
from typing import Any

from app.aplicacao.ia.json_ia import extrair_objeto_json
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.dominio.entidades.ia_rag import ConfigIAConta, FonteRAG
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.portas.ia_meta import ClienteIAPort

_NUCLEO_ESTRUTURAL_GLOBAL = (
    "[NÚCLEO ESTRUTURAL GLOBAL]\n"
    "Você é estrategista especialista em Instagram e criação de conteúdo autoral.\n"
    "Regras invariáveis: responda sempre em Português do Brasil; seja fiel aos fatos da conta; "
    "nunca invente preços, endereços, prazos ou promessas não presentes no contexto; "
    "adapte o texto exatamente ao formato solicitado (IMAGE, CAROUSEL, REELS ou STORIES)."
)


def compilar_brand_bible_deterministica(
    conta: ContaInstagram,
    config: ConfigIAConta,
    fontes: list[FonteRAG],
) -> dict[str, Any]:
    """Compila resumo compacto da identidade da conta combinando persona, templates e RAG."""
    p = config.persona_json
    existente = dict(config.brand_bible_json or {})
    fatos_rag = [
        (f.resumo_fatos or f"[{f.titulo}] {f.chunks[0][:180]}")[:240]
        for f in fontes[:5]
        if f.resumo_fatos or f.chunks
    ]
    compilada: dict[str, Any] = {
        "conta_username": f"@{conta.username}",
        "marca": str(p.get("marca") or f"@{conta.username}"),
        "nicho": str(p.get("nicho") or "criação de conteúdo no Instagram"),
        "regiao": str(p.get("regiao") or "Brasil"),
        "publico_alvo": str(p.get("publico_alvo") or "seguidores engajados"),
        "tom_voz": str(p.get("tom_voz") or "autêntico, claro e envolvente"),
        "cta_padrao": str(p.get("cta_padrao") or "convite natural para comentar ou salvar"),
        "restricoes": str(
            p.get("restricoes") or "não inventar preços, dados ou promessas irreais"
        ),
        "templates_ativos": sorted(str(k) for k in config.templates_json),
        "fatos_chave_rag": fatos_rag,
    }
    for chave_extra in (
        "posicionamento",
        "pilares_conteudo",
        "diretrizes_visuais",
        "regras_nao_fazer",
    ):
        if existente.get(chave_extra):
            compilada[chave_extra] = existente[chave_extra]
    return compilada


def formatar_templates_conta(templates_json: dict[str, Any]) -> str:
    """Converte templates_json da conta em instruções estáveis para a geração."""
    if not templates_json:
        return ""
    linhas: list[str] = []
    for chave, valor in sorted(templates_json.items(), key=lambda item: str(item[0])):
        if valor is None or valor == "" or valor == [] or valor == {}:
            continue
        if isinstance(valor, (dict, list)):
            serializado = json.dumps(valor, ensure_ascii=False, sort_keys=True)
        else:
            serializado = str(valor).strip()
        linhas.append(f"- {chave}: {serializado[:400]}")
    return "\n".join(linhas)


def montar_system_prompt_com_brand_bible(
    conta: ContaInstagram,
    config: ConfigIAConta,
) -> str:
    """Combina núcleo global cacheável com persona, Brand Bible e templates da conta."""
    p = config.persona_json
    marca = str(p.get("marca") or f"@{conta.username}")
    nicho = str(p.get("nicho") or "criação de conteúdo no Instagram")
    regiao = str(p.get("regiao") or "Brasil")
    tom = str(p.get("tom_voz") or "autêntico, claro e envolvente")
    publico = str(p.get("publico_alvo") or "seguidores engajados")
    cta = str(p.get("cta_padrao") or "convite natural para comentar ou salvar")
    restricoes = str(p.get("restricoes") or "não inventar preços, dados ou promessas irreais")

    blocos = [
        _NUCLEO_ESTRUTURAL_GLOBAL,
        (
            f"[IDENTIDADE DA CONTA @{conta.username} ({marca})]\n"
            f"Nicho: {nicho} | Região: {regiao} | Público: {publico}.\n"
            f"Tom de voz: {tom}.\n"
            f"CTA preferencial: {cta}.\n"
            f"Restrições obrigatórias: {restricoes}."
        ),
    ]
    if config.brand_bible_json:
        bible_txt = json.dumps(config.brand_bible_json, ensure_ascii=False, sort_keys=True)
        blocos.append(f"[BRAND BIBLE PRÉ-COMPILADA DA CONTA]\n{bible_txt[:2200]}")
    templates_txt = formatar_templates_conta(config.templates_json)
    if templates_txt:
        blocos.append(f"[TEMPLATES ATIVOS DA CONTA]\n{templates_txt[:1500]}")
    return "\n\n".join(blocos)


def montar_prompts_brand_bible_ia(base: dict[str, Any]) -> tuple[str, str]:
    """Retorna (system_prompt, user_prompt) para enriquecimento da Brand Bible via IA."""
    sys_p = "Compile Brand Bibles JSON concisas para contas Instagram em PT-BR."
    usr_p = (
        f"Dados da conta: {base}\nRetorne JSON com: "
        '"posicionamento" (str), "pilares_conteudo" (lista str), '
        '"diretrizes_visuais" (str), "regras_nao_fazer" (lista str).'
    )
    return sys_p, usr_p


def mesclar_brand_bible_ia(base: dict[str, Any], bruto_ia: str) -> dict[str, Any]:
    """Mescla campos válidos retornados pela IA sobre a Brand Bible determinística."""
    return {**base, **{k: v for k, v in extrair_objeto_json(bruto_ia).items() if v}}


def formatar_ancoras_visuais_lista(midias: list[MidiaBiblioteca], limite: int = 4) -> str:
    """Prioriza mídias curtidas (curtida_favorita=True) como referência estética."""
    ordenadas = sorted(midias, key=lambda m: (m.curtida_favorita, m.criado_em), reverse=True)
    linhas = [
        f"- [{'FAVORITA' if m.curtida_favorita else m.pasta.value}] "
        f"{m.resumo_visual.strip() or m.chave_storage.rsplit('/', 1)[-1]}"
        for m in ordenadas[:limite]
    ]
    return "\n".join(linhas) if linhas else "Sem referências visuais catalogadas ainda."


async def enriquecer_brand_bible_com_ia(
    conta: ContaInstagram, config: ConfigIAConta, base: dict[str, Any],
    cliente_ia: ClienteIAPort, orcamento: ServicoOrcamentoUseCase | None,
) -> dict[str, Any]:
    """Enriquece Brand Bible determinística via IA respeitando BudgetGuard."""
    modelo = config.modelo_texto_pref
    if orcamento is not None:
        dec = await orcamento.decidir_politica_chamada(
            conta.empresa_id, modelo, estimar_chamada(modelo)
        )
        modelo = dec.modelo_efetivo
    sys_p, usr_p = montar_prompts_brand_bible_ia(base)
    bruto, usage = await cliente_ia.gerar_texto(sys_p, usr_p, modelo, formato_json=True)
    if orcamento is not None:
        await orcamento.registrar_consumo(conta.empresa_id, conta.id, usage)
    return mesclar_brand_bible_ia(base, bruto)
