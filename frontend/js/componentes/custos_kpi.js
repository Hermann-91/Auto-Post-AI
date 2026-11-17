import { el, limpar } from "/painel/js/dom.js";
import { criarIcone } from "/painel/js/icones.js";

function formatarUsd(valor) {
  const num = Number(valor ?? 0);
  if (!Number.isFinite(num)) return "$0.00";
  const casas = num > 0 && num < 0.01 ? 4 : 2;
  return `$${num.toFixed(casas)}`;
}

function criarKpiCard({ rotulo, valor, subtexto, icone, classeTom = "", badge = null }) {
  return el("div", { className: `kpi-card${classeTom ? ` ${classeTom}` : ""}` }, [
    el("div", { className: "kpi-topo" }, [
      el("span", { className: "kpi-label", text: rotulo }),
      criarIcone(icone, { tamanho: 16, classe: "muted" }),
    ]),
    badge || el("strong", { className: "kpi-valor", text: valor }),
    el("span", { className: "small muted kpi-sub", text: subtexto }),
  ]);
}

export function aplicarCorProgresso(barra, percentual) {
  if (!barra) return;
  const pct = Math.max(0, Math.min(100, Number(percentual) || 0));
  barra.style.width = `${pct}%`;
  barra.classList.toggle("progress-warn", pct >= 75 && pct < 95);
  barra.classList.toggle("progress-danger", pct >= 95);
}

/**
 * Renderiza os cards de KPIs e barra de consumo da aba Custos.
 */
export function renderizarPainelCustos(orc) {
  if (!orc) return;
  const pct = Math.max(0, Number(orc.percentual_usado) || 0);
  const periodoEl = document.getElementById("custos-periodo-badge");
  if (periodoEl && orc.mes && orc.ano) {
    periodoEl.textContent = `Competência ${String(orc.mes).padStart(2, "0")}/${orc.ano}`;
  }

  aplicarCorProgresso(document.getElementById("orcamento-bar"), pct);

  const det = document.getElementById("orcamento-detalhe");
  if (det) {
    const modoTxt = orc.bloqueio_orcamento ? "Bloqueio estrito" : "Fallback gratuito";
    det.textContent = `Empresa: ${formatarUsd(orc.gasto_empresa_usd)} / ${formatarUsd(orc.limite_mensal_usd)} USD (${pct.toFixed(1)}%) • Conta ativa: ${formatarUsd(orc.gasto_conta_usd)} • ${modoTxt}`;
  }

  const grid = document.getElementById("custos-kpis-grid");
  if (!grid) return;
  limpar(grid);
  const tomSaldo = pct >= 95 ? "kpi-danger" : pct >= 75 ? "kpi-warn" : "kpi-ok";
  const badgeModo = el("span", {
    className: `badge kpi-badge-valor ${orc.bloqueio_orcamento ? "badge-warn" : "badge-ok"}`,
    text: orc.bloqueio_orcamento ? "Bloqueio estrito" : "Fallback gratuito",
  });

  grid.append(
    criarKpiCard({
      rotulo: "Gasto da Empresa (Mês)",
      valor: formatarUsd(orc.gasto_empresa_usd),
      subtexto: `Limite mensal: ${formatarUsd(orc.limite_mensal_usd)} USD`,
      icone: "dollarSign",
    }),
    criarKpiCard({
      rotulo: "Conta Ativa",
      valor: formatarUsd(orc.gasto_conta_usd),
      subtexto: "Consumo acumulado desta conta",
      icone: "layers",
    }),
    criarKpiCard({
      rotulo: "Saldo Disponível",
      valor: formatarUsd(orc.saldo_disponivel_usd),
      subtexto: `${pct.toFixed(1)}% do teto mensal usado`,
      icone: "database",
      classeTom: tomSaldo,
    }),
    criarKpiCard({
      rotulo: "Modo de Proteção",
      badge: badgeModo,
      subtexto: orc.bloqueio_orcamento
        ? "Interrompe chamadas pagas ao atingir 100%"
        : "Alterna para modelo gratuito no teto",
      icone: "shield",
    })
  );
}
