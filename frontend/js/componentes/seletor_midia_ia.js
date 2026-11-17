import { apiFetch } from "/painel/js/api.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

export const PRESETS_MELHORIA = [
  { id: "fullhd", label: "Melhorar Resolução (FullHD)" },
  { id: "foto_profissional", label: "Fotografia Profissional" },
  { id: "iluminacao", label: "Iluminação Melhorada (HDR)" },
];

function miniPreviewMidia(contaId, midia, className = "") {
  const url = `/biblioteca/${contaId}/midias/${midia.id}/conteudo`;
  return midia.tipo_arquivo.startsWith("video/")
    ? el("video", { src: url, className, muted: "true" })
    : el("img", { src: url, className, alt: midia.pasta || "Mídia", loading: "lazy" });
}

async function renderizarGridBiblioteca(boxGrid, contaId, estado, aoSelecionar) {
  if (!contaId) return boxGrid.appendChild(el("p", { className: "small muted", text: "Selecione uma conta." }));
  try {
    const itens = await apiFetch(`/biblioteca/${contaId}`);
    limpar(boxGrid);
    const apenasVideo = estado.aceitar.startsWith("video/");
    const filtrados = (itens || []).filter((m) => !apenasVideo || m.tipo_arquivo.startsWith("video/"));
    if (!filtrados.length) return boxGrid.appendChild(el("p", { className: "small muted", text: "Nenhuma mídia compatível na Biblioteca." }));
    for (const m of filtrados) {
      const ativa = estado.selecionadas.some((s) => s.id === m.id);
      const btn = el("button", { type: "button", className: `seletor-thumb-btn ${ativa ? "selecionada" : ""}`, title: m.resumo_visual || m.pasta }, [miniPreviewMidia(contaId, m)]);
      btn.addEventListener("click", () => aoSelecionar(m));
      boxGrid.appendChild(btn);
    }
  } catch (err) {
    notificar(err.message, "erro");
  }
}

function montarPainelMelhoria(estado, mostrarLogo, notificarMudanca) {
  if (estado.bloquearIA) return null;
  if (estado.modo !== "ia" && !estado.selecionadas.length) return null;
  const chips = PRESETS_MELHORIA.map((p) => {
    const chk = el("input", { type: "checkbox" });
    chk.checked = estado.presets.has(p.id);
    chk.addEventListener("change", () => {
      if (chk.checked) estado.presets.add(p.id); else estado.presets.delete(p.id);
      notificarMudanca();
    });
    return el("label", { className: "presets-chip" }, [chk, el("span", { text: p.label })]);
  });
  if (mostrarLogo) {
    const chkLogo = el("input", { type: "checkbox" });
    chkLogo.checked = estado.aplicarLogo;
    chkLogo.addEventListener("change", () => { estado.aplicarLogo = chkLogo.checked; notificarMudanca(); });
    chips.push(el("label", { className: "presets-chip" }, [chkLogo, el("span", { text: "Aplicar Logo da Marca" })]));
  }
  const inputExtra = el("input", { type: "text", placeholder: "Instruções extras para melhoria da imagem...", value: estado.promptExtra });
  inputExtra.addEventListener("input", () => { estado.promptExtra = inputExtra.value; notificarMudanca(); });
  const dica = estado.selecionadas.length
    ? "✨ Melhorar Imagem Anexada com IA (sem presets/instrução, usa a foto original a $0)"
    : "✨ Ajustes Ópticos & Estúdio IA";
  return el("div", { className: "stack-sm" }, [el("span", { className: "small muted", text: dica }), el("div", { className: "seletor-presets" }, chips), inputExtra]);
}

export function criarSeletorMidiaIA({ idContainer, containerEl = null, obterContaAtiva, multiplo = false, permitirModoIA = true, mostrarLogo = false, aoMudar = null }) {
  const raiz = containerEl || document.getElementById(idContainer);
  if (!raiz) return null;
  const estado = {
    modo: permitirModoIA ? "ia" : "biblioteca",
    selecionadas: [],
    presets: new Set(),
    promptExtra: "",
    aplicarLogo: false,
    bloquearIA: false,
    aceitar: "image/jpeg,image/png,image/webp,video/mp4,video/quicktime",
  };
  const obterEstado = () => ({
    modo: estado.modo,
    midiaIdsSelecionadas: estado.selecionadas.map((m) => m.id),
    midiasSelecionadas: [...estado.selecionadas],
    presetsMelhoria: [...estado.presets],
    promptExtra: estado.promptExtra.trim(),
    aplicarLogo: estado.aplicarLogo,
  });
  const notificarMudanca = () => aoMudar && aoMudar(obterEstado());

  const alternarMidia = (item) => {
    const existe = estado.selecionadas.some((m) => m.id === item.id);
    if (existe) estado.selecionadas = estado.selecionadas.filter((m) => m.id !== item.id);
    else estado.selecionadas = multiplo ? [...estado.selecionadas, item] : [item];
    renderizar();
    notificarMudanca();
  };

  async function enviarArquivos(arquivos) {
    const contaId = obterContaAtiva();
    if (!contaId || !arquivos.length) return;
    for (const arq of (multiplo ? [...arquivos] : [arquivos[0]])) {
      const fd = new FormData();
      fd.append("pasta", "originais");
      fd.append("arquivo", arq);
      try {
        const salva = await apiFetch(`/biblioteca/${contaId}/upload`, { method: "POST", body: fd });
        estado.selecionadas = multiplo ? [...estado.selecionadas, salva] : [salva];
        notificar(`Arquivo "${arq.name}" anexado à Biblioteca.`);
      } catch (err) { notificar(err.message, "erro"); }
    }
    renderizar();
    notificarMudanca();
  }

  function renderizar() {
    limpar(raiz);
    const modos = [...(permitirModoIA && !estado.bloquearIA ? [["ia", "🤖 Criar do Zero (IA)"]] : []), ["pc", "💻 Anexar PC/Mobile"], ["biblioteca", "🗂️ Da Biblioteca"]];
    raiz.appendChild(el("div", { className: "seletor-modos" }, modos.map(([id, label]) => {
      const btn = el("button", { type: "button", className: `tab-btn small ${estado.modo === id ? "active" : ""}`, text: label });
      btn.addEventListener("click", () => {
        estado.modo = id;
        if (id === "ia") estado.selecionadas = [];
        renderizar();
        notificarMudanca();
      });
      return btn;
    })));
    if (estado.modo === "pc") {
      const inputArq = el("input", { type: "file", accept: estado.aceitar });
      if (multiplo) inputArq.setAttribute("multiple", "multiple");
      inputArq.addEventListener("change", () => enviarArquivos(inputArq.files || []));
      raiz.appendChild(inputArq);
    }
    if (estado.modo === "biblioteca") {
      const grid = el("div", { className: "seletor-bib-lista" });
      raiz.appendChild(grid);
      renderizarGridBiblioteca(grid, obterContaAtiva(), estado, alternarMidia);
    }
    if (estado.selecionadas.length) {
      const contaId = obterContaAtiva();
      const btnLimpar = el("button", { type: "button", className: "btn-ghost small", text: "Limpar" });
      btnLimpar.addEventListener("click", () => { estado.selecionadas = []; renderizar(); notificarMudanca(); });
      raiz.appendChild(el("div", { className: "row-actions" }, [
        el("span", { className: "badge badge-ok", text: `${estado.selecionadas.length} selecionada(s)` }),
        ...estado.selecionadas.slice(0, 4).map((m) => miniPreviewMidia(contaId, m, "plano-mini-img")),
        btnLimpar,
      ]));
    }
    if (permitirModoIA || mostrarLogo) {
      const painel = montarPainelMelhoria(estado, mostrarLogo, notificarMudanca);
      if (painel) raiz.appendChild(painel);
    }
  }

  renderizar();
  return {
    obterEstado,
    recarregar: () => renderizar(),
    limparSelecao: () => { estado.selecionadas = []; estado.presets.clear(); estado.promptExtra = ""; estado.aplicarLogo = false; renderizar(); },
    definirRestricao: ({ bloquearIA = false, aceitar = "image/jpeg,image/png,image/webp,video/mp4,video/quicktime" }) => {
      estado.bloquearIA = bloquearIA;
      estado.aceitar = aceitar;
      if (bloquearIA && estado.modo === "ia") estado.modo = "biblioteca";
      renderizar();
    },
  };
}
