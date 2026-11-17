import { apiJson } from "/painel/js/api.js";
import { criarSeletorMidiaIA } from "/painel/js/componentes/seletor_midia_ia.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

const MODOS = [["SO_TEXTO", "📝 Só Texto (Planejar 1º)"], ["IA_COMPLETA", "✨ IA Completa"], ["MANUAL_ZERO", "📷 Manual $0"]];
const FORMATOS = [["IMAGE", "Feed"], ["CAROUSEL", "Carrossel"], ["REELS", "Reels"], ["STORIES", "Stories"]];
const PILARES = ["Educativo", "Bastidores", "Autoridade", "Prova Social", "Oferta", "Tendência"];

function proximaSegundaISO() {
  const d = new Date();
  d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7));
  return d.toISOString().slice(0, 10);
}

export function criarEstudioUnificado({ raiz, obterContaAtiva, aoSubmeter }) {
  if (!raiz) return null;
  limpar(raiz);

  const estado = {
    modo: "IA_COMPLETA", quantidades: { IMAGE: 1, CAROUSEL: 0, REELS: 0, STORIES: 0 },
    pilares: new Set(), modoSerie: false, autoAgendar: false, ocupado: false, seletor: null,
  };

  const form = el("form", { id: "form-estudio-unificado", className: "stack-sm" });
  const boxModos = el("div", { className: "tabs-inline" });
  const badgeTotal = el("span", { className: "badge badge-ok" });
  const boxQuantidades = el("div", { className: "estudio-grid-formatos" });
  const boxPilares = el("div", { className: "estudio-pilares" });
  const inpTema = el("textarea", { name: "tema", rows: "2", placeholder: "Tema opcional (ou selecione um Pilar acima)..." });
  const inpEtapaSerie = el("input", { name: "etapa_serie", type: "text", className: "hidden", placeholder: "Etapa da série (ex.: Parte 1/3)" });
  const chkSerie = el("input", { type: "checkbox", name: "modo_serie" });
  const chkAutoAgendar = el("input", { type: "checkbox", name: "auto_agendar" });
  const inpSemana = el("input", { name: "semana_inicio", type: "date", value: proximaSegundaISO() });
  const inpAgendarPara = el("input", { name: "agendar_para", type: "datetime-local" });
  const boxAgendaLote = el("label", { className: "hidden" }, [el("span", { text: "Início da Semana" }), inpSemana]);
  const boxAgendaUnit = el("label", {}, [el("span", { text: "Agendar (opcional)" }), inpAgendarPara]);
  const boxSeletor = el("div", { id: "seletor-midia-semanal", className: "seletor-midia-box" });
  const btnCurarLote = el("button", { type: "button", className: "btn-ghost btn-sm hidden", text: "🏆 IA Eleger Melhor Foto" });

  const txtAvancado = el("textarea", { name: "prompt_avancado", rows: "2", placeholder: "Direção visual ou instrução extra opcional..." });
  const inpTom = el("input", { name: "tom_extra", type: "text", placeholder: "Ex.: mais direto" });
  const inpNicho = el("input", { name: "nicho", type: "text", placeholder: "Nicho (usa Persona se vazio)" });
  const inpRegiao = el("input", { name: "regiao", type: "text", placeholder: "Brasil" });
  const detalhesAvancado = el("details", { className: "estudio-avancado" }, [
    el("summary", { text: "⚙️ Prompt Avançado Opcional (Direção, Tom, Nicho/Região)" }),
    el("div", { className: "stack-sm" }, [
      txtAvancado,
      el("div", { className: "row-actions" }, [
        el("label", {}, [el("span", { text: "Tom Extra" }), inpTom]),
        el("label", {}, [el("span", { text: "Nicho" }), inpNicho]),
        el("label", {}, [el("span", { text: "Região" }), inpRegiao]),
      ]),
    ]),
  ]);
  const btnSubmit = el("button", { type: "submit", className: "btn-primary" });

  const totalItens = () => Object.values(estado.quantidades).reduce((a, b) => a + b, 0);

  function atualizarUI() {
    const total = totalItens();
    const ehLote = total > 1 && estado.modo !== "MANUAL_ZERO";
    badgeTotal.textContent = `${total} ${total === 1 ? "publicação" : "publicações"}`;
    boxAgendaLote.classList.toggle("hidden", !ehLote);
    boxAgendaUnit.classList.toggle("hidden", ehLote);
    inpEtapaSerie.classList.toggle("hidden", !estado.modoSerie);
    inpTema.placeholder = estado.modo === "MANUAL_ZERO"
      ? "Legenda manual (vazio para Stories)..."
      : "Tema opcional (Zero-Prompt: ou escolha um Pilar acima)...";
    for (const b of boxModos.querySelectorAll("button")) b.classList.toggle("active", b.dataset.modo === estado.modo);
    const temAnexo = (estado.seletor?.obterEstado().midiaIdsSelecionadas.length || 0) >= 2;
    btnCurarLote.classList.toggle("hidden", !temAnexo || estado.modo === "MANUAL_ZERO");
    btnSubmit.disabled = estado.ocupado;
    if (estado.ocupado) {
      btnSubmit.textContent = "⏳ Processando job em segundo plano...";
      return;
    }
    if (estado.modo === "MANUAL_ZERO") btnSubmit.textContent = "📅 Enviar Manual p/ Agenda ($0)";
    else if (ehLote) btnSubmit.textContent = "📊 Propor Grade & Orçamento ($)";
    else btnSubmit.textContent = estado.modo === "SO_TEXTO" ? "📝 Gerar Rascunho Só-Texto" : "✨ Gerar Post com IA";
  }

  MODOS.forEach(([id, label]) => {
    const btn = el("button", { type: "button", className: "tab-btn small", "data-modo": id, text: label });
    btn.addEventListener("click", () => { estado.modo = id; atualizarUI(); });
    boxModos.appendChild(btn);
  });

  const inputsQtd = {};
  FORMATOS.forEach(([fmt, label]) => {
    const inp = el("input", { type: "number", min: "0", max: "14", value: String(estado.quantidades[fmt]) });
    inputsQtd[fmt] = inp;
    inp.addEventListener("input", () => { estado.quantidades[fmt] = Math.max(0, Math.min(14, Number(inp.value) || 0)); atualizarUI(); });
    boxQuantidades.appendChild(el("label", { className: "estudio-fmt-card" }, [el("span", { className: "small", text: label }), inp]));
  });

  const aplicarPresetQtd = (mapa) => {
    for (const [k] of FORMATOS) {
      estado.quantidades[k] = mapa[k] || 0;
      inputsQtd[k].value = String(estado.quantidades[k]);
    }
    atualizarUI();
  };
  const atalhos = el("div", { className: "row-actions" }, [
    badgeTotal,
    ...[["1 Post", { IMAGE: 1 }], ["Mix 5", { IMAGE: 3, REELS: 1, STORIES: 1 }], ["Semana 7", { IMAGE: 3, CAROUSEL: 2, REELS: 1, STORIES: 1 }]].map(([t, m]) => {
      const b = el("button", { type: "button", className: "btn-ghost btn-sm", text: t });
      b.addEventListener("click", () => aplicarPresetQtd(m));
      return b;
    }),
  ]);

  PILARES.forEach((pilar) => {
    const chip = el("button", { type: "button", className: "pilar-chip", text: pilar });
    chip.addEventListener("click", () => {
      if (estado.pilares.has(pilar)) estado.pilares.delete(pilar);
      else estado.pilares.add(pilar);
      chip.classList.toggle("active", estado.pilares.has(pilar));
    });
    boxPilares.appendChild(chip);
  });

  chkSerie.addEventListener("change", () => { estado.modoSerie = chkSerie.checked; atualizarUI(); });
  chkAutoAgendar.addEventListener("change", () => { estado.autoAgendar = chkAutoAgendar.checked; });
  btnCurarLote.addEventListener("click", async () => {
    const contaId = obterContaAtiva();
    const ids = estado.seletor?.obterEstado().midiaIdsSelecionadas || [];
    if (!contaId || ids.length < 2) return;
    btnCurarLote.setAttribute("disabled", "disabled");
    try {
      const res = await apiJson(`/ia/curadoria/${contaId}/eleger-melhor`, "POST", {
        midia_ids: ids.slice(0, 5), objetivo_contexto: inpTema.value.trim(),
      });
      notificar(`Foto #${res.indice_vencedora} eleita: ${res.justificativa}`);
    } catch (err) { notificar(err.message, "erro"); }
    finally { btnCurarLote.removeAttribute("disabled"); }
  });

  form.append(
    boxModos, atalhos, boxQuantidades,
    el("div", { className: "stack-sm" }, [el("span", { className: "small muted", text: "Pilares Editoriais (opcional)" }), boxPilares]),
    inpTema,
    el("div", { className: "row-actions" }, [
      el("label", { className: "check small" }, [chkSerie, el("span", { text: "Modo Série Narrativa" })]),
      el("label", { className: "check small" }, [chkAutoAgendar, el("span", { text: "Auto-agendar na grade" })]),
    ]),
    inpEtapaSerie,
    el("div", { className: "row-actions" }, [boxAgendaLote, boxAgendaUnit]),
    boxSeletor, btnCurarLote, detalhesAvancado, btnSubmit
  );
  raiz.appendChild(form);

  estado.seletor = criarSeletorMidiaIA({
    containerEl: boxSeletor, obterContaAtiva, multiplo: true, permitirModoIA: false, mostrarLogo: true,
    aoMudar: () => atualizarUI(),
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (estado.ocupado) return;
    const total = totalItens();
    if (total < 1 || total > 14) return notificar("Defina entre 1 e 14 publicações.", "erro");
    const sel = estado.seletor.obterEstado();
    aoSubmeter({
      modo: estado.modo, quantidades: { ...estado.quantidades }, total,
      pilares: [...estado.pilares], modoSerie: estado.modoSerie,
      etapaSerie: inpEtapaSerie.value.trim(), tema: inpTema.value.trim(),
      autoAgendar: estado.autoAgendar, semanaInicio: inpSemana.value,
      agendarPara: inpAgendarPara.value, promptAvancado: txtAvancado.value.trim(),
      tomExtra: inpTom.value.trim(), nicho: inpNicho.value.trim(), regiao: inpRegiao.value.trim(),
      midiaIds: sel.midiaIdsSelecionadas, midias: sel.midiasSelecionadas,
      presetsMelhoria: sel.presetsMelhoria, promptExtraVisual: sel.promptExtra, aplicarLogo: sel.aplicarLogo,
    });
  });

  atualizarUI();
  return {
    definirOcupado: (v) => { estado.ocupado = Boolean(v); atualizarUI(); },
    limparMidias: () => { estado.seletor?.limparSelecao(); atualizarUI(); },
    recarregarSeletor: () => estado.seletor?.recarregar(),
  };
}
