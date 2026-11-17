import { apiFetch, apiJson } from "/painel/js/api.js";
import { criarEstadoVazio } from "/painel/js/componentes/estado_vazio.js";
import { el, limpar, notificar } from "/painel/js/dom.js";
import { criarIcone, iconeTexto } from "/painel/js/icones.js";

const ICONE_POR_TIPO = { URL: "globe", REFERENCIA_BENCHMARK: "bookOpen" };

function envolverCardFormulario(icone, titulo, form) {
  return el("section", { className: "rag-form-card" }, [
    el("div", { className: "rag-card-head" }, [criarIcone(icone, { tamanho: 16 }), el("strong", { text: titulo })]),
    form,
  ]);
}

function criarFormularioRagTexto() {
  const selTipo = el("select", { name: "tipo", "aria-label": "Tipo da fonte" }, [
    el("option", { value: "TEXTO", text: "TEXTO" }),
    el("option", { value: "FAQ", text: "FAQ" }),
    el("option", { value: "DOCUMENTO", text: "DOCUMENTO" }),
  ]);
  const inpTitulo = el("input", { name: "titulo", type: "text", placeholder: "Título da fonte", required: "true" });
  const inpConteudo = el("textarea", {
    name: "conteudo", rows: "2", placeholder: "Cole diretrizes, FAQs ou fatos da marca...", required: "true",
  });
  const btn = el("button", { type: "submit", className: "btn-primary btn-inline-icone" }, iconeTexto("plus", "Indexar Texto", { tamanho: 15 }));
  return envolverCardFormulario("fileText", "Texto ou FAQ", el("form", { id: "form-rag", className: "stack-sm" }, [
    el("div", { className: "rag-form-dupla" }, [selTipo, inpTitulo]),
    inpConteudo,
    btn,
  ]));
}

function criarFormularioRagArquivo() {
  const selTipo = el("select", { name: "tipo", "aria-label": "Tipo do documento" }, [
    el("option", { value: "DOCUMENTO", text: "DOCUMENTO" }),
    el("option", { value: "FAQ", text: "FAQ" }),
    el("option", { value: "REFERENCIA_BENCHMARK", text: "BENCHMARK" }),
  ]);
  const inpTitulo = el("input", { name: "titulo", type: "text", placeholder: "Título opcional" });
  const inpArq = el("input", {
    name: "arquivo", type: "file", accept: ".pdf,.txt,.md,application/pdf,text/plain,text/markdown", required: "true",
  });
  const btn = el("button", { type: "submit", className: "btn-outline btn-inline-icone" }, iconeTexto("upload", "Enviar PDF/TXT/MD", { tamanho: 15 }));
  return envolverCardFormulario("upload", "Documento (PDF, TXT, MD)", el("form", { id: "form-rag-arquivo", className: "stack-sm" }, [
    el("div", { className: "rag-form-dupla" }, [selTipo, inpTitulo]),
    inpArq,
    btn,
  ]));
}

function criarFormularioRagUrl() {
  const selTipo = el("select", { name: "tipo", "aria-label": "Tipo da URL" }, [
    el("option", { value: "URL", text: "URL Pública" }),
    el("option", { value: "REFERENCIA_BENCHMARK", text: "Benchmark de Formato" }),
  ]);
  const inpUrl = el("input", { name: "url", type: "url", placeholder: "https://site.com/artigo", required: "true" });
  const inpTitulo = el("input", { name: "titulo", type: "text", placeholder: "Título opcional" });
  const btn = el("button", { type: "submit", className: "btn-outline btn-inline-icone" }, iconeTexto("globe", "Indexar URL", { tamanho: 15 }));
  return envolverCardFormulario("globe", "Página Web / Benchmark", el("form", { id: "form-rag-url", className: "stack-sm" }, [
    el("div", { className: "rag-form-dupla" }, [selTipo, inpTitulo]),
    inpUrl,
    btn,
  ]));
}

function criarCardFonteRag(f, contaId) {
  const btnDel = el("button", {
    type: "button", className: "btn-danger-outline btn-sm btn-inline-icone", title: "Excluir fonte RAG",
  }, iconeTexto("trash", "Excluir", { tamanho: 13 }));
  btnDel.addEventListener("click", async () => {
    btnDel.setAttribute("disabled", "disabled");
    try {
      await apiFetch(`/contas/${contaId}/rag/${f.id}`, { method: "DELETE" });
      notificar("Fonte RAG removida.");
      await carregarRag(contaId);
    } catch (err) {
      notificar(err.message, "erro");
      btnDel.removeAttribute("disabled");
    }
  });
  const dataTxt = f.criado_em ? new Date(f.criado_em).toLocaleDateString("pt-BR") : "";
  return el("article", { className: "rag-card" }, [
    el("div", { className: "row-between" }, [
      el("div", { className: "rag-card-head" }, [
        criarIcone(ICONE_POR_TIPO[f.tipo] || "fileText", { tamanho: 16 }),
        el("strong", { text: f.titulo }),
      ]),
      btnDel,
    ]),
    el("div", { className: "row-actions" }, [
      el("span", { className: "badge", text: f.tipo }),
      el("span", { className: f.tem_embeddings ? "badge badge-ok" : "badge", text: f.tem_embeddings ? "Embeddings" : "Lexical" }),
      el("span", { className: "small muted", text: `${f.total_chunks} chunk(s)` }),
      dataTxt ? el("span", { className: "small muted", text: `• ${dataTxt}` }) : null,
    ]),
    f.resumo_fatos ? el("p", { className: "small muted rag-resumo", text: f.resumo_fatos }) : null,
  ]);
}

function renderizarFontes(boxRag, fontes, contaId) {
  limpar(boxRag);
  if (!fontes || !fontes.length) {
    boxRag.appendChild(criarEstadoVazio({
      icone: "bookOpen",
      titulo: "Nenhuma fonte RAG indexada nesta conta.",
      descricao: "Indexe textos, PDFs ou URLs acima para enriquecer legendas e Brand Bible com o contexto da marca.",
      acaoLabel: "Indexar primeira fonte",
      acaoIcone: "plus",
      aoAcionar: () => document.querySelector("#form-rag input[name='titulo']")?.focus(),
    }));
    return;
  }
  const lista = el("div", { className: "rag-lista-grid" }, fontes.map((f) => criarCardFonteRag(f, contaId)));
  boxRag.append(el("span", { className: "small muted", text: `Base indexada (${fontes.length})` }), lista);
}

export async function carregarRag(contaId) {
  const boxRag = document.getElementById("lista-rag");
  if (!contaId || !boxRag) return;
  const fontes = await apiFetch(`/contas/${contaId}/rag`);
  renderizarFontes(boxRag, fontes, contaId);
}

async function executarComBloqueio(form, fn) {
  const btn = form.querySelector("button[type='submit']");
  btn?.setAttribute("disabled", "disabled");
  try { await fn(); } finally { btn?.removeAttribute("disabled"); }
}

export function inicializarRag(obterContaAtiva) {
  const root = document.getElementById("rag-painel-root");
  if (!root) return;
  limpar(root);
  root.className = "rag-ingestao-grid";
  root.append(criarFormularioRagTexto(), criarFormularioRagArquivo(), criarFormularioRagUrl());

  const fTexto = document.getElementById("form-rag");
  const fArquivo = document.getElementById("form-rag-arquivo");
  const fUrl = document.getElementById("form-rag-url");

  fTexto?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const fd = new FormData(fTexto);
    await executarComBloqueio(fTexto, async () => {
      try {
        await apiJson(`/contas/${contaId}/rag`, "POST", {
          tipo: String(fd.get("tipo") || "TEXTO"),
          titulo: String(fd.get("titulo") || ""),
          conteudo: String(fd.get("conteudo") || ""),
        });
        notificar("Fonte RAG indexada.");
        fTexto.reset();
        await carregarRag(contaId);
      } catch (err) { notificar(err.message, "erro"); }
    });
  });

  fArquivo?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const fd = new FormData(fArquivo);
    await executarComBloqueio(fArquivo, async () => {
      try {
        await apiFetch(`/contas/${contaId}/rag/arquivo`, { method: "POST", body: fd });
        notificar("Arquivo extraído e indexado na base RAG!");
        fArquivo.reset();
        await carregarRag(contaId);
      } catch (err) { notificar(err.message, "erro"); }
    });
  });

  fUrl?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const fd = new FormData(fUrl);
    await executarComBloqueio(fUrl, async () => {
      try {
        await apiJson(`/contas/${contaId}/rag/url`, "POST", {
          url: String(fd.get("url") || ""),
          tipo: String(fd.get("tipo") || "URL"),
          titulo: String(fd.get("titulo") || ""),
        });
        notificar("URL extraída e indexada na base RAG!");
        fUrl.reset();
        await carregarRag(contaId);
      } catch (err) { notificar(err.message, "erro"); }
    });
  });
}
