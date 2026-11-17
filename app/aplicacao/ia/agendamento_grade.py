"""Helpers puros de composição dinâmica de formatos e cálculo UTC para auto-agendamento."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.aplicacao.ia.grade_semanal import montar_cmd_item_grade
from app.dominio.entidades.publicacao import PlanejamentoSemanal, Postagem
from app.dominio.excecoes import ErroDominio, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import StatusPlanejamento, TipoMidia

if TYPE_CHECKING:
    from app.aplicacao.ia.criar_conteudo import CriarConteudoUseCase

FUSO_HORARIO_PADRAO = "America/Sao_Paulo"
_REGEX_HORA = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_DIAS_SEMANA_OFFSET: dict[str, int] = {
    "segunda": 0, "seg": 0, "segunda-feira": 0,
    "terca": 1, "ter": 1, "terca-feira": 1,
    "quarta": 2, "qua": 2, "quarta-feira": 2,
    "quinta": 3, "qui": 3, "quinta-feira": 3,
    "sexta": 4, "sex": 4, "sexta-feira": 4,
    "sabado": 5, "sab": 5,
    "domingo": 6, "dom": 6,
}


def _normalizar_texto(texto: str) -> str:
    decomposed = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def validar_fuso_horario(fuso_horario: str | None) -> ZoneInfo:
    """Valida e retorna ZoneInfo IANA (padrão America/Sao_Paulo)."""
    nome = (fuso_horario or FUSO_HORARIO_PADRAO).strip() or FUSO_HORARIO_PADRAO
    try:
        return ZoneInfo(nome)
    except ZoneInfoNotFoundError as exc:
        raise ErroValidacaoDominio(f"Fuso horário IANA inválido: '{nome}'.") from exc


def validar_e_expandir_composicao(
    composicao_formatos: dict[str, int] | None,
    quantidade_posts: int,
) -> tuple[int, list[TipoMidia]]:
    """Valida composição dinâmica (ex.: 3 IMAGE + 2 REELS) e retorna total e sequência."""
    if not composicao_formatos:
        if not 1 <= quantidade_posts <= 14:
            raise ErroValidacaoDominio("Quantidade de posts da semana deve estar entre 1 e 14.")
        return quantidade_posts, []

    sequencia: list[TipoMidia] = []
    for chave, qtd in composicao_formatos.items():
        try:
            tipo = TipoMidia(str(chave).strip().upper())
        except ValueError as exc:
            raise ErroValidacaoDominio(f"Formato inválido na composição: '{chave}'.") from exc
        if qtd < 0:
            raise ErroValidacaoDominio("Quantidade por formato não pode ser negativa.")
        sequencia.extend([tipo] * qtd)

    total = len(sequencia)
    if not 1 <= total <= 14:
        raise ErroValidacaoDominio(
            "Composição de formatos da semana deve totalizar entre 1 e 14 publicações."
        )
    return total, sequencia


def _resolver_offset_dia(dia_semana: str, ordem: int) -> int:
    chave = _normalizar_texto(dia_semana)
    for token, offset in _DIAS_SEMANA_OFFSET.items():
        if chave == token or chave.startswith(f"{token} "):
            return offset
    return max(0, ordem - 1) % 7


def _resolver_hora_minuto(horario_sugerido: str) -> time:
    match = _REGEX_HORA.search(str(horario_sugerido or ""))
    if not match:
        return time(18, 0)
    return time(int(match.group(1)), int(match.group(2)))


def calcular_agendado_para_utc(
    semana_inicio: date,
    item: dict[str, Any],
    fuso_horario: str | None,
    indice_ordem: int,
) -> datetime:
    """Converte semana_inicio + dia_semana + horario_sugerido no fuso da conta para UTC."""
    zona = validar_fuso_horario(fuso_horario)
    offset = _resolver_offset_dia(str(item.get("dia_semana") or ""), indice_ordem)
    data_alvo = semana_inicio + timedelta(days=offset)
    hora = _resolver_hora_minuto(str(item.get("horario_sugerido") or "18:00"))
    local_dt = datetime.combine(data_alvo, hora, tzinfo=zona)
    return local_dt.astimezone(UTC)


def preparar_reexecucao_plano(plano: PlanejamentoSemanal) -> None:
    """Reabre planos concluídos ou falhos para nova execução de mídia e rascunhos."""
    if plano.status not in {StatusPlanejamento.CONCLUIDO, StatusPlanejamento.FALHA}:
        return
    plano.status = StatusPlanejamento.APROVADO
    for it in plano.itens_grade:
        if (
            isinstance(it, dict)
            and str(it.get("formato") or "").upper() != "REELS"
            and not it.get("midia_base_ids")
        ):
            it["usar_ia_imagem"] = True


async def executar_itens_grade(
    plano: PlanejamentoSemanal,
    criador: CriarConteudoUseCase,
    auto_agendar: bool | None = None,
    fuso_horario: str | None = None,
    ao_progredir: Callable[[int, int, str], Awaitable[None]] | None = None,
) -> tuple[list[Postagem], list[str], Decimal]:
    """Executa itens da grade semanal e aplica auto-agendamento UTC quando habilitado."""
    cfg_plano = plano.tendencias_cache.get("_config_plano") or {}
    agendar_ativo = (
        bool(cfg_plano.get("auto_agendar", False)) if auto_agendar is None else auto_agendar
    )
    fuso_efetivo = fuso_horario or str(cfg_plano.get("fuso_horario") or FUSO_HORARIO_PADRAO)

    postagens: list[Postagem] = []
    falhas: list[str] = []
    custo_real = Decimal("0")
    total = len(plano.itens_grade)

    for idx, item in enumerate(plano.itens_grade, start=1):
        try:
            if ao_progredir is not None:
                tema = str(item.get("tema") or f"Item {idx}")[:50]
                await ao_progredir(idx - 1, total, f"Gerando item {idx}/{total}: {tema}")
            dt_utc = (
                calcular_agendado_para_utc(plano.semana_inicio, item, fuso_efetivo, idx)
                if agendar_ativo
                else None
            )
            cmd_item = montar_cmd_item_grade(
                plano.empresa_id, plano.conta_ig_id, plano.id, item, agendar_para=dt_utc
            )
            res = await criador.executar(cmd_item)
            custo_real += res.custo_total_usd
            if res.postagem is not None:
                postagens.append(res.postagem)
                if agendar_ativo and not res.postagem.midias_chaves:
                    falhas.append(
                        f"Item {item.get('ordem', idx)}: mantido em RASCUNHO (sem mídia)."
                    )
        except ErroDominio as exc:
            falhas.append(f"Item {item.get('ordem', '?')}: {exc}")
        if ao_progredir is not None:
            await ao_progredir(idx, total, f"Concluído item {idx}/{total}")

    return postagens, falhas, custo_real
