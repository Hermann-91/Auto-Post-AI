"""Diretor de Arte Documental: gera SceneSpec estruturado e sanitiza prompts visuais."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.aplicacao.ia.dtos_visuais import SceneSpec
from app.aplicacao.ia.json_ia import extrair_objeto_json
from app.aplicacao.ia.prompts_brand_bible import formatar_ancoras_visuais_lista
from app.aplicacao.ia.servico_orcamento import ServicoOrcamentoUseCase, estimar_chamada
from app.dominio.entidades.ia_rag import ConfigIAConta
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroIntegracaoIA
from app.dominio.objetos_valor.enums_conteudo import TipoMidia
from app.dominio.portas.ia_meta import ClienteIAPort

MAPA_PROMPT_PRESETS: dict[str, str] = {
    "fullhd": "sharp optical focus, natural micro-texture, authentic lens detail",
    "foto_profissional": "documentary 35mm photography, natural depth of field, candid realism",
    "iluminacao": "soft natural directional daylight, organic shadows, true-to-life exposure",
}

_PADRAO_CLICHES = re.compile(
    r"\b(?:8k|4k|full\s*hd|ultra\s+high\s+resolution|hdr|hyper[-\s]*realistic|"
    r"photorealistic|unreal\s+engine|octane\s+render|3d\s+render|cgi|masterpiece|"
    r"trending\s+on\s+artstation|commercial\s+grade|professional\s+studio\s+photography|"
    r"studio\s+lighting|studio)\b",
    re.IGNORECASE,
)

_REGRAS_FOTOGRAFIA_GLOBAL = (
    "[REGRAS GLOBAIS DE DIREÇÃO DE ARTE DOCUMENTAL]\n"
    "Você é Diretor de Arte especializado em fotografia documental real para Instagram.\n"
    "Regras invariáveis:\n"
    "1. Descreva cenas reais capturadas em câmera 35mm/50mm/85mm com luz natural/ambiente.\n"
    "2. Valorize texturas orgânicas autênticas (pele natural, tecidos, objetos cotidianos).\n"
    "3. NUNCA use clichês artificiais: 8k, fullhd, HDR, studio lighting, CGI, hyperrealistic.\n"
    "4. Não invente texto sobreposto, letras aleatórias, logotipos espúrios ou mãos extras.\n"
    "5. Varie ângulo, lente e iluminação em relação ao histórico, salvo quando em Modo Série."
)


def sanitizar_prompt_visual(texto: str) -> str:
    """Remove jargões plásticos/CGI e normaliza pontuação residual."""
    limpo = _PADRAO_CLICHES.sub("", texto)
    limpo = re.sub(r"\s*,\s*,+", ", ", limpo)
    limpo = re.sub(r"\s{2,}", " ", limpo)
    return limpo.strip(" ,.")


def compilar_prompt_geracao(
    prompt_base: str,
    prompt_avancado: str = "",
    prompt_visual_extra: str = "",
    presets_melhoria: tuple[str, ...] = (),
    instrucao_correcao: str = "",
) -> str:
    """Monta prompt final limpo sem duplicações ou clichês artificiais."""
    partes: list[str] = []
    vistas: set[str] = set()
    for bruto in (prompt_base, prompt_avancado, prompt_visual_extra):
        limpo = sanitizar_prompt_visual(bruto)
        chave = limpo.lower()
        if limpo and chave not in vistas:
            partes.append(limpo)
            vistas.add(chave)
    tags = [
        MAPA_PROMPT_PRESETS[p.lower()]
        for p in presets_melhoria
        if p.lower() in MAPA_PROMPT_PRESETS
    ]
    if tags:
        partes.append(", ".join(tags))
    if instrucao_correcao.strip():
        partes.append(f"Correção visual obrigatória: {sanitizar_prompt_visual(instrucao_correcao)}")
    return ". ".join(partes).strip(" .")


class DiretorArteService:
    """Gera SceneSpec JSON estruturado isolado por conta Instagram."""

    def __init__(self, cliente_ia: ClienteIAPort, orcamento: ServicoOrcamentoUseCase) -> None:
        self._ia = cliente_ia
        self._orcamento = orcamento

    @staticmethod
    def _identidade_visual_conta(conta: ContaInstagram, config: ConfigIAConta) -> str:
        bible = config.brand_bible_json or {}
        persona = config.persona_json or {}
        marca = str(bible.get("marca") or persona.get("marca") or f"@{conta.username}")
        nicho = str(bible.get("nicho") or persona.get("nicho") or "conteúdo autoral")
        diretrizes = str(
            bible.get("diretrizes_visuais")
            or persona.get("diretrizes_visuais")
            or "fotografia documental natural fiel ao cotidiano real da marca"
        )
        paleta = str(persona.get("paleta_cores") or bible.get("posicionamento") or "tons naturais")
        return (
            f"Conta: @{conta.username} ({marca}) | Nicho: {nicho}\n"
            f"Diretrizes visuais da conta: {diretrizes[:400]}\n"
            f"Paleta e posicionamento: {paleta[:250]}"
        )

    @staticmethod
    def _construir_scene_spec(
        dados: dict[str, Any], tema: str, pilar_editorial: str,
        modo_serie: bool, etapa_serie: str, prompt_avancado: str,
    ) -> SceneSpec:
        sujeito = sanitizar_prompt_visual(str(dados.get("sujeito_principal") or tema))
        acao = sanitizar_prompt_visual(str(dados.get("acao_e_narrativa") or "momento espontâneo"))
        ambiente = sanitizar_prompt_visual(str(dados.get("ambiente") or "ambiente cotidiano real"))
        lente = sanitizar_prompt_visual(
            str(dados.get("enquadramento_lente") or "plano médio, lente 35mm documental")
        )
        luz = sanitizar_prompt_visual(
            str(dados.get("iluminacao") or "luz natural suave lateral de janela")
        )
        clima = sanitizar_prompt_visual(
            str(dados.get("paleta_e_clima") or "cores orgânicas equilibradas")
        )
        bruto_evitar = dados.get("evitar")
        evitar = (
            tuple(str(x).strip() for x in bruto_evitar if str(x).strip())
            if isinstance(bruto_evitar, list)
            else ("texto borrado", "mãos deformadas", "estética plástica")
        )
        bruto_prompt = sanitizar_prompt_visual(str(dados.get("prompt_imagem_final") or ""))
        if not bruto_prompt:
            bruto_prompt = sanitizar_prompt_visual(
                f"{sujeito}, {acao}, {ambiente}, {lente}, {luz}, {clima}"
            )
        if prompt_avancado.strip():
            av = sanitizar_prompt_visual(prompt_avancado)
            if av.lower() not in bruto_prompt.lower():
                bruto_prompt = f"{bruto_prompt}. {av}".strip(" .")
        return SceneSpec(
            sujeito_principal=sujeito, acao_e_narrativa=acao, ambiente=ambiente,
            enquadramento_lente=lente, iluminacao=luz, paleta_e_clima=clima,
            evitar=evitar, prompt_imagem_final=bruto_prompt, modo_serie=modo_serie,
            etapa_serie=etapa_serie, pilar_editorial=pilar_editorial,
        )

    async def dirigir_cena(
        self, conta: ContaInstagram, config: ConfigIAConta, tema: str, objetivo: str,
        tipo_midia: TipoMidia, proporcao: str, resumo_copy: str,
        midias_recentes: list[MidiaBiblioteca], pilar_editorial: str = "",
        modo_serie: bool = False, etapa_serie: str = "", prompt_avancado: str = "",
        tem_referencia_real: bool = False, modelo_texto: str | None = None,
    ) -> tuple[SceneSpec, Decimal, str]:
        """Planeja cena documental estruturada (SceneSpec) isolada por conta."""
        identidade = self._identidade_visual_conta(conta, config)
        system_prompt = f"{_REGRAS_FOTOGRAFIA_GLOBAL}\n\n[IDENTIDADE VISUAL]\n{identidade}"
        historico = formatar_ancoras_visuais_lista(
            midias_recentes, limite=5, modo_serie=modo_serie
        )
        bloco_serie = (
            f"MODO SÉRIE ATIVO | Etapa atual: {etapa_serie or 'continuidade sequencial'}.\n"
            if modo_serie
            else "MODO POST ÚNICO: varie enquadramento, lente e luz do histórico recente.\n"
        )
        bloco_ref = (
            "REFERÊNCIA REAL ANEXADA: preserve fielmente o objeto/pessoa real das fotos base.\n"
            if tem_referencia_real
            else ""
        )
        user_prompt = (
            f"Formato: {tipo_midia.value} | Proporção: {proporcao} | Tema: {tema}\n"
            f"Objetivo: {objetivo} | Pilar: {pilar_editorial or 'geral'}\n"
            f"Intenção da copy (apenas referência semântica): {resumo_copy[:220]}\n"
            f"{bloco_serie}{bloco_ref}"
            f"Direção opcional do usuário: {prompt_avancado or 'nenhuma'}\n"
            f"Histórico visual da conta:\n{historico}\n\n"
            'Retorne JSON com chaves: "sujeito_principal", "acao_e_narrativa", "ambiente", '
            '"enquadramento_lente", "iluminacao", "paleta_e_clima", "evitar" (lista str), '
            '"prompt_imagem_final" (descrição fotográfica direta sem clichês).'
        )
        modelo = (modelo_texto or config.modelo_texto_pref).strip()
        decisao = await self._orcamento.decidir_politica_chamada(
            conta.empresa_id, modelo, estimar_chamada(modelo), exige_imagem_paga=False
        )
        bruto, usage = await self._ia.gerar_texto(
            system_prompt, user_prompt, decisao.modelo_efetivo, formato_json=True
        )
        reg = await self._orcamento.registrar_consumo(conta.empresa_id, conta.id, usage)
        try:
            dados = extrair_objeto_json(bruto)
        except ErroIntegracaoIA:
            dados = {}
        spec = self._construir_scene_spec(
            dados, tema, pilar_editorial, modo_serie, etapa_serie, prompt_avancado
        )
        return spec, reg.custo_usd, reg.modelo
