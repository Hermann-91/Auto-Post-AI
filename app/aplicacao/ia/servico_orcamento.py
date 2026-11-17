"""Controle rigoroso de orçamento em USD (BudgetGuard) e contabilização OpenRouter."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.aplicacao.ia.dtos import DecisaoOrcamentoDTO, ResumoOrcamentoDTO
from app.dominio.entidades.ia_rag import RegistroCustoIA
from app.dominio.excecoes import ErroOrcamentoExcedido, ErroValidacaoDominio
from app.dominio.portas.repositorios_conteudo import CustoRepositoryPort
from app.dominio.portas.repositorios_tenant import EmpresaRepositoryPort

CUSTOS_ESTIMADOS_USD: dict[str, Decimal] = {
    "openrouter/free": Decimal("0.0000"),
    "deepseek/deepseek-v4-flash": Decimal("0.0020"),
    "google/gemini-2.5-flash-lite": Decimal("0.0015"),
    "google/gemini-3.1-flash-lite-image": Decimal("0.0200"),
    "google/gemini-3.1-flash-image": Decimal("0.0450"),
}
_CUSTO_PADRAO_TEXTO = Decimal("0.0050")
_CUSTO_PADRAO_IMAGEM = Decimal("0.0450")
_MODELO_VISAO_PADRAO = "google/gemini-2.5-flash-lite"
MAX_LOOPS_CRITICA_VISUAL = 2


def _modelo_eh_gratuito(modelo: str) -> bool:
    return modelo == "openrouter/free" or modelo.endswith(":free")


def estimar_chamada(modelo: str, eh_imagem: bool = False) -> Decimal:
    """Estima custo unitário conservador em USD para pré-validação e planos."""
    if _modelo_eh_gratuito(modelo):
        return Decimal("0.0000")
    if modelo in CUSTOS_ESTIMADOS_USD:
        return CUSTOS_ESTIMADOS_USD[modelo]
    return _CUSTO_PADRAO_IMAGEM if eh_imagem else _CUSTO_PADRAO_TEXTO


def estimar_pipeline_visual(
    modelo_imagem: str,
    modelo_visao: str = _MODELO_VISAO_PADRAO,
    max_loops: int = MAX_LOOPS_CRITICA_VISUAL,
    incluir_regeneracao: bool = True,
) -> Decimal:
    """Estima teto conservador do pipeline visual com até N loops de crítica VLM."""
    loops = max(1, max_loops)
    geracoes = loops if incluir_regeneracao else 1
    custo_img = estimar_chamada(modelo_imagem, eh_imagem=True) * geracoes
    custo_vis = estimar_chamada(modelo_visao, eh_imagem=False) * loops
    return (custo_img + custo_vis).quantize(Decimal("0.0001"))


def estimar_plano_semanal(
    itens: list[dict[str, Any]],
    modelo_texto: str,
    modelo_imagem: str,
    modelo_visao: str | None = None,
) -> Decimal:
    """Calcula estimativa total em USD da Etapa 2 antes da aprovação do usuário."""
    total = Decimal("0.0000")
    custo_txt = estimar_chamada(modelo_texto, eh_imagem=False)
    custo_visao = estimar_chamada(modelo_visao or _MODELO_VISAO_PADRAO, eh_imagem=False)
    custo_img = (
        estimar_pipeline_visual(modelo_imagem, modelo_visao)
        if modelo_visao
        else estimar_chamada(modelo_imagem, eh_imagem=True)
    )
    for item in itens:
        formato = str(item.get("formato") or "IMAGE").upper()
        total += custo_txt
        usar_ia = bool(item.get("usar_ia_imagem", False)) and formato != "REELS"
        if usar_ia:
            total += custo_img
        elif item.get("midia_base_ids"):
            total += custo_visao
    return total.quantize(Decimal("0.0001"))


class ServicoOrcamentoUseCase:
    """Aplica limites mensais por empresa, fallback econômico e registro real de custos."""

    def __init__(
        self,
        empresa_repo: EmpresaRepositoryPort,
        custo_repo: CustoRepositoryPort,
        modelo_fallback_free: str = "openrouter/free",
        relogio: Callable[[], datetime] | None = None,
    ) -> None:
        self._empresa_repo = empresa_repo
        self._custo_repo = custo_repo
        self._modelo_fallback_free = modelo_fallback_free
        self._relogio = relogio or (lambda: datetime.now(UTC))

    async def _obter_empresa_e_gasto(self, empresa_id: UUID) -> tuple[Decimal, bool, Decimal]:
        empresa = await self._empresa_repo.buscar_por_id(empresa_id)
        if empresa is None:
            raise ErroValidacaoDominio("Empresa não encontrada para checagem de orçamento.")
        agora = self._relogio()
        gasto_atual = await self._custo_repo.somar_mes_empresa(empresa_id, agora.year, agora.month)
        return empresa.limite_mensal_usd, empresa.bloqueio_orcamento, gasto_atual

    async def verificar_disponibilidade(self, empresa_id: UUID, custo_previsto: Decimal) -> bool:
        """Implementa OrcamentoCheckerPort validando saldo do mês corrente."""
        if custo_previsto < Decimal("0"):
            raise ErroValidacaoDominio("Custo previsto não pode ser negativo.")
        limite, _, gasto_atual = await self._obter_empresa_e_gasto(empresa_id)
        if gasto_atual >= limite:
            return False
        return (gasto_atual + custo_previsto) <= limite

    async def decidir_politica_chamada(
        self, empresa_id: UUID, modelo_desejado: str, custo_estimado: Decimal,
        exige_imagem_paga: bool = False,
    ) -> DecisaoOrcamentoDTO:
        """Resolve modelo permitido ou bloqueia conforme modo estrito/econômico."""
        limite, bloqueio_estrito, gasto_atual = await self._obter_empresa_e_gasto(empresa_id)

        def _decisao(modelo: str, eco: bool) -> DecisaoOrcamentoDTO:
            return DecisaoOrcamentoDTO(True, modelo, eco, gasto_atual, limite)

        if _modelo_eh_gratuito(modelo_desejado):
            return _decisao(modelo_desejado, False)
        estourou = gasto_atual >= limite or (gasto_atual + custo_estimado) > limite
        if not estourou:
            return _decisao(modelo_desejado, False)
        if bloqueio_estrito:
            raise ErroOrcamentoExcedido(
                f"Limite mensal de ${limite} USD atingido (gasto atual: ${gasto_atual})."
            )
        if exige_imagem_paga:
            raise ErroOrcamentoExcedido(
                "Limite mensal atingido: geração de imagem paga bloqueada no modo econômico."
            )
        return _decisao(self._modelo_fallback_free, True)

    async def registrar_consumo(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        usage: dict[str, Any],
        postagem_id: UUID | None = None,
    ) -> RegistroCustoIA:
        """Persiste tokens e custo real em USD extraído da resposta OpenRouter."""
        gen_id = str(usage.get("openrouter_gen_id") or "").strip() or f"local-{uuid4().hex[:10]}"
        custo = usage.get("custo_usd", Decimal("0"))
        custo_dec = custo if isinstance(custo, Decimal) else Decimal(str(custo))
        registro = RegistroCustoIA(
            empresa_id=empresa_id,
            conta_ig_id=conta_ig_id,
            postagem_id=postagem_id,
            openrouter_gen_id=gen_id,
            modelo=str(usage.get("modelo") or "desconhecido"),
            tokens_in=max(0, int(usage.get("tokens_in") or 0)),
            tokens_out=max(0, int(usage.get("tokens_out") or 0)),
            custo_usd=max(Decimal("0"), custo_dec),
            criado_em=self._relogio(),
        )
        return await self._custo_repo.registrar(registro)

    async def obter_resumo_mensal(
        self, empresa_id: UUID, conta_ig_id: UUID | None = None
    ) -> ResumoOrcamentoDTO:
        """Retorna resumo mensal de gastos em USD da empresa e opcionalmente da conta IG."""
        limite, bloqueio, gasto_emp = await self._obter_empresa_e_gasto(empresa_id)
        agora = self._relogio()
        gasto_conta = Decimal("0")
        if conta_ig_id is not None:
            gasto_conta = await self._custo_repo.somar_mes_por_conta(
                empresa_id, conta_ig_id, agora.year, agora.month
            )
        saldo = max(Decimal("0.0000"), limite - gasto_emp)
        pct = (
            100.0
            if limite == Decimal("0")
            else round(min(100.0, float((gasto_emp / limite) * 100)), 2)
        )
        return ResumoOrcamentoDTO(
            empresa_id=empresa_id,
            conta_ig_id=conta_ig_id,
            ano=agora.year,
            mes=agora.month,
            limite_mensal_usd=limite,
            gasto_empresa_usd=gasto_emp,
            gasto_conta_usd=gasto_conta,
            saldo_disponivel_usd=saldo,
            percentual_usado=pct,
            bloqueio_orcamento=bloqueio,
        )
