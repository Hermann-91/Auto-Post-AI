import { apiFetch, apiJson, executarJobIA } from "/painel/js/api.js";
import { criarCardItemGrade } from "/painel/js/componentes/item_grade.js";
import { el, limpar, notificar } from "/painel/js/dom.js";
import { criarIcone, iconeTexto } from "/painel/js/icones.js";

const STATUS_META = {
  AGUARDANDO_APROVACAO: { rotulo: "Aguardando Aprovação", classe: "badge-warn" },
  APROVADO: { rotulo: "Aprovado", classe: "badge-info" },
  EM_EXECUCAO: { rotulo: "Em Execução", classe: "badge-info" },
  CONCLUIDO: { rotulo: "Concluído", classe: "badge-ok" },
  FALHA: { rotulo: "Falha", classe: "badge-danger" },
  RASCUNHO: { rotulo: "Rascunho", classe: "" },
};

function descreverStatus(status) {
  if (STATUS_META[status]) return STATUS_META[status];
  const texto = (status || "Pendente").toLowerCase().replaceAll("_", " ");
  return { rotulo: texto.replace(/\b\w/g, (c) => c.toUpperCase()), classe: "" };
}

function resumirFormatos(itens) {
  const contagem = new Map();
  for (const it of itens) {
    const fmt = it.formato || "IMAGE";
    contagem.set(fmt, (contagem.get(fmt) || 0) + 1);
  }
  return [...contagem.entries()].map(([fmt, qtd]) =>
    el("span", { className: `badge-fmt fmt-${fmt.toLowerCase()}`, text: `${qtd} ${fmt}` })
  );
}

function criarSeletorLote(planos, planoAtivo, aoTrocar) {
  const sel = el("select", { className: "grades-select-lote", "aria-label": "Selecionar lote de grade programada" }, planos.map((p) => {
    const qtd = (p.itens_grade || []).length;
    const un = qtd === 1 ? "item" : "itens";
    const extraStatus = planos.length > 1 ? ` • ${descreverStatus(p.status).rotulo}` : "";
    const opt = el("option", { value: p.id, text: `Semana ${p.semana_inicio} • ${qtd} ${un} • Est. $${p.custo_estimado_usd} USD${extraStatus}` });
    if (p.id === planoAtivo.id) opt.selected = true;
    return opt;
  }));
  sel.addEventListener("change", () => aoTrocar(sel.value));
  return sel;
}

export function renderizarResumoSemanal({
  container, planos, contaId, midiaPorId, planoSelecionadoId, aoAtualizar,
  aoExecutarPlano = null, aoSelecionarPlano = null,
}) {
  if (!container) return;
  limpar(container);
  if (!planos.length) {
    container.classList.add("hidden");
    return;
  }
  container.classList.remove("hidden");

  const plano = planos.find((p) => p.id === planoSelecionadoId) || planos[0];
  const itensEditados = (plano.itens_grade || []).map((it) => ({ ...it }));
  const editavel = ["AGUARDANDO_APROVACAO", "APROVADO", "RASCUNHO"].includes(plano.status);
  const emExecucao = plano.status === "EM_EXECUCAO";
  const metaStatus = descreverStatus(plano.status);

  const seletor = criarSeletorLote(planos, plano, (novoId) => {
    aoSelecionarPlano?.(novoId);
    renderizarResumoSemanal({
      container, planos, contaId, midiaPorId, planoSelecionadoId: novoId,
      aoAtualizar, aoExecutarPlano, aoSelecionarPlano,
    });
  });

  const dispararExecucao = async (btn) => {
    if (aoExecutarPlano) return aoExecutarPlano(plano, editavel ? itensEditados : null, btn);
    btn.setAttribute("disabled", "disabled");
    try {
      if (editavel) await apiJson(`/planejamento/${contaId}/${plano.id}/itens`, "PATCH", { itens_grade: itensEditados });
      const job = await executarJobIA({ contaId, tipoJob: "EXECUTAR_PLANO", payload: { executar_plano: { plano_id: plano.id } }, chaveIdempotencia: `exec-${plano.id}-${Date.now()}` });
      notificar(`Concluído! ${(job.resultado_json?.postagens_criadas || []).length} post(s) na Agenda.`);
      await aoAtualizar(plano.id);
    } catch (err) { notificar(err.message, "erro"); }
    finally { btn.removeAttribute("disabled"); }
  };

  const btnAcao = editavel
    ? el("button", { type: "button", className: "btn-aprovar-grade btn-inline-icone" }, iconeTexto("check", "Aprovar & Gerar na Agenda", { tamanho: 15 }))
    : el("button", { type: "button", className: "btn-outline btn-inline-icone" }, iconeTexto("refresh", emExecucao ? "Em Execução..." : "Gerar Novamente", { tamanho: 15 }));
  if (emExecucao) btnAcao.setAttribute("disabled", "disabled");
  else btnAcao.addEventListener("click", () => dispararExecucao(btnAcao));

  const btnExcluir = el("button", { type: "button", className: "btn-danger-outline btn-inline-icone" }, iconeTexto("trash", "Excluir Lote", { tamanho: 15 }));
  if (emExecucao) {
    btnExcluir.setAttribute("disabled", "disabled");
    btnExcluir.title = "Aguarde a execução concluir para excluir este lote.";
  } else {
    btnExcluir.addEventListener("click", async () => {
      if (!window.confirm(`Excluir o lote da semana ${plano.semana_inicio}? Esta ação não apaga postagens já enviadas à Agenda.`)) return;
      btnExcluir.setAttribute("disabled", "disabled");
      try {
        await apiFetch(`/planejamento/${contaId}/${plano.id}`, { method: "DELETE" });
        notificar("Lote de grade excluído.");
        await aoAtualizar("");
      } catch (err) {
        notificar(err.message, "erro");
        btnExcluir.removeAttribute("disabled");
      }
    });
  }

  const cabecalho = el("div", { className: "grades-header" }, [
    el("div", { className: "grades-header-info" }, [
      el("div", { className: "grades-header-titulo" }, [
        criarIcone("layers", { tamanho: 18 }),
        el("h3", { text: "Grades Programadas" }),
      ]),
      seletor,
    ]),
    el("div", { className: "grades-header-acoes" }, [
      el("span", { className: `badge ${metaStatus.classe}`.trim(), text: metaStatus.rotulo }),
      btnAcao,
      btnExcluir,
    ]),
  ]);

  const corpoDetalhes = [
    el("div", { className: "grade-itens-grid" }, itensEditados.map((item, indice) =>
      criarCardItemGrade({ item, indice, editavel, contaId, midiaPorId })
    )),
  ];
  if (editavel) {
    const btnSalvar = el("button", { type: "button", className: "btn-outline btn-sm btn-inline-icone" }, iconeTexto("check", "Salvar Ajustes da Grade", { tamanho: 14 }));
    btnSalvar.addEventListener("click", async () => {
      btnSalvar.setAttribute("disabled", "disabled");
      try {
        const atual = await apiJson(`/planejamento/${contaId}/${plano.id}/itens`, "PATCH", { itens_grade: itensEditados });
        notificar(`Ajustes salvos! Novo orçamento: $${atual.custo_estimado_usd} USD.`);
        await aoAtualizar(plano.id);
      } catch (err) { notificar(err.message, "erro"); }
      finally { btnSalvar.removeAttribute("disabled"); }
    });
    corpoDetalhes.push(el("div", { className: "grade-detalhes-rodape" }, [btnSalvar]));
  }

  const acordeao = el("details", { className: "grade-detalhes" }, [
    el("summary", { className: "grade-detalhes-summary" }, [
      el("span", { className: "grade-summary-esq" }, [
        criarIcone("chevronRight", { tamanho: 16, classe: "grade-chevron" }),
        el("span", { text: `Revisar e editar itens da grade (${itensEditados.length})` }),
      ]),
      el("span", { className: "grade-formatos-resumo" }, resumirFormatos(itensEditados)),
    ]),
    el("div", { className: "grade-detalhes-corpo" }, corpoDetalhes),
  ]);

  container.append(cabecalho, acordeao);
}
