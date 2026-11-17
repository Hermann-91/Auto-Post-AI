import { apiFetch, apiJson } from "/painel/js/api.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

function criarFormularioRagTexto() {
  const selTipo = el("select", { name: "tipo" }, [
    el("option", { value: "TEXTO", text: "TEXTO" }),
    el("option", { value: "FAQ", text: "FAQ" }),
    el("option", { value: "DOCUMENTO", text: "DOCUMENTO" }),
  ]);
  const inpTitulo = el("input", { name: "titulo", type: "text", placeholder: "Título da fonte", required: "true" });
  const inpConteudo = el("input", { name: "conteudo", type: "text", placeholder: "Conteúdo de referência da marca...", required: "true" });
  const btn = el("button", { type: "submit", className: "btn-primary", text: "Indexar Texto" });
  return el("form", { id: "form-rag", className: "row-actions" }, [selTipo, inpTitulo, inpConteudo, btn]);
}

function criarFormularioRagArquivo() {
  const selTipo = el("select", { name: "tipo" }, [
    el("option", { value: "DOCUMENTO", text: "DOCUMENTO" }),
    el("option", { value: "FAQ", text: "FAQ" }),
    el("option", { value: "REFERENCIA_BENCHMARK", text: "BENCHMARK" }),
  ]);
  const inpTitulo = el("input", { name: "titulo", type: "text", placeholder: "Título opcional" });
  const inpArq = el("input", {
    name: "arquivo", type: "file", accept: ".pdf,.txt,.md,application/pdf,text/plain,text/markdown", required: "true",
  });
  const btn = el("button", { type: "submit", className: "btn-outline", text: "📄 Enviar PDF/TXT/MD" });
  return el("form", { id: "form-rag-arquivo", className: "row-actions" }, [selTipo, inpTitulo, inpArq, btn]);
}

function criarFormularioRagUrl() {
  const selTipo = el("select", { name: "tipo" }, [
    el("option", { value: "URL", text: "URL Pública" }),
    el("option", { value: "REFERENCIA_BENCHMARK", text: "Benchmark de Formato" }),
  ]);
  const inpUrl = el("input", { name: "url", type: "url", placeholder: "https://site.com/artigo", required: "true" });
  const inpTitulo = el("input", { name: "titulo", type: "text", placeholder: "Título opcional" });
  const btn = el("button", { type: "submit", className: "btn-outline", text: "🌐 Indexar URL" });
  return el("form", { id: "form-rag-url", className: "row-actions" }, [selTipo, inpUrl, inpTitulo, btn]);
}

function renderizarFontes(boxRag, fontes, contaId) {
  limpar(boxRag);
  if (!fontes || !fontes.length) {
    boxRag.appendChild(el("p", { className: "muted small", text: "Nenhuma fonte RAG indexada nesta conta." }));
    return;
  }
  for (const f of fontes) {
    const btnDel = el("button", { type: "button", className: "btn-danger btn-sm", text: "Excluir" });
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
    const badges = [
      el("span", { className: "badge", text: f.tipo }),
      el("span", { className: f.tem_embeddings ? "badge badge-ok" : "badge", text: f.tem_embeddings ? "Embeddings" : "Lexical" }),
      el("span", { className: "small muted", text: `${f.total_chunks} chunk(s)` }),
    ];
    boxRag.appendChild(el("div", { className: "item-card row-between" }, [
      el("div", { className: "stack-sm" }, [
        el("div", { className: "row-actions" }, [el("strong", { text: f.titulo }), ...badges]),
        f.resumo_fatos ? el("p", { className: "small muted", text: f.resumo_fatos }) : null,
      ]),
      btnDel,
    ]));
  }
}

export async function carregarRag(contaId) {
  const boxRag = document.getElementById("lista-rag");
  if (!contaId || !boxRag) return;
  const fontes = await apiFetch(`/contas/${contaId}/rag`);
  renderizarFontes(boxRag, fontes, contaId);
}

async function executarComBloqueio(form, fn) {
  const btn = form.querySelector("button[type='submit']");
  if (btn) btn.setAttribute("disabled", "disabled");
  try {
    await fn();
  } finally {
    if (btn) btn.removeAttribute("disabled");
  }
}

export function inicializarRag(obterContaAtiva) {
  const root = document.getElementById("rag-painel-root");
  if (!root) return;
  limpar(root);
  const fTexto = criarFormularioRagTexto();
  const fArquivo = criarFormularioRagArquivo();
  const fUrl = criarFormularioRagUrl();
  root.appendChild(fTexto);
  root.appendChild(fArquivo);
  root.appendChild(fUrl);

  fTexto.addEventListener("submit", async (e) => {
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

  fArquivo.addEventListener("submit", async (e) => {
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

  fUrl.addEventListener("submit", async (e) => {
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
