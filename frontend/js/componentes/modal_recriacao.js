import { apiFetch, apiJson } from "/painel/js/api.js";
import { criarSeletorMidiaIA, PRESETS_MELHORIA } from "/painel/js/componentes/seletor_midia_ia.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

function criarBaseModal(titulo) {
  const backdrop = el("div", { className: "modal-backdrop", role: "dialog", "aria-modal": "true" });
  const btnFechar = el("button", { type: "button", className: "btn-ghost small", text: "✕ Fechar" });
  const card = el("div", { className: "modal-card" }, [
    el("div", { className: "row-between" }, [el("h3", { text: titulo }), btnFechar]),
  ]);
  backdrop.appendChild(card);

  const fechar = () => {
    document.removeEventListener("keydown", aoEsc);
    backdrop.remove();
  };
  const aoEsc = (e) => { if (e.key === "Escape") fechar(); };
  btnFechar.addEventListener("click", fechar);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) fechar(); });
  document.addEventListener("keydown", aoEsc);
  document.body.appendChild(backdrop);
  return { card, fechar };
}

async function carregarCulturaRag(boxRag, contaId) {
  try {
    const fontes = await apiFetch(`/contas/${contaId}/rag`);
    limpar(boxRag);
    boxRag.appendChild(el("strong", { className: "small", text: "📚 Cultura da Conta (RAG) aplicada:" }));
    if (!fontes || !fontes.length) {
      boxRag.appendChild(el("p", { className: "small muted", text: "Nenhuma fonte RAG cadastrada; será usada a Persona da conta." }));
      return;
    }
    for (const f of fontes.slice(0, 4)) {
      const trecho = (f.chunks && f.chunks[0]) ? `: ${f.chunks[0].slice(0, 120)}...` : "";
      boxRag.appendChild(el("p", { className: "small", text: `• [${f.tipo}] ${f.titulo}${trecho}` }));
    }
  } catch {
    limpar(boxRag);
    boxRag.appendChild(el("p", { className: "small muted", text: "Não foi possível carregar a Cultura RAG." }));
  }
}

export async function abrirModalRecriacao({ post, alvo, contaId, midiaAtual, promptAtual, aoConcluir }) {
  const ehImagem = alvo === "imagem";
  const { card, fechar } = criarBaseModal(ehImagem ? "✨ Recriar / Melhorar Imagem (IA + RAG)" : "✍️ Recriar Legenda (IA + RAG)");

  if (ehImagem) {
    const url = midiaAtual ? `/biblioteca/${contaId}/midias/${midiaAtual.id}/conteudo` : "";
    const preview = midiaAtual
      ? (midiaAtual.tipo_arquivo.startsWith("video/")
        ? el("video", { src: url, className: "modal-preview-img", controls: "true" })
        : el("img", { src: url, className: "modal-preview-img", alt: "Imagem atual" }))
      : el("p", { className: "small muted", text: "Este card ainda não possui imagem; será gerada uma nova." });
    card.appendChild(preview);
    if (promptAtual) card.appendChild(el("p", { className: "small muted", text: `🎨 Prompt atual: ${promptAtual}` }));
  } else {
    card.appendChild(el("div", { className: "post-texto-box" }, [
      el("span", { className: "small muted", text: "Texto atual da postagem:" }),
      el("p", { className: "post-legenda-txt", text: post.legenda || "(Sem legenda)" }),
    ]));
  }

  const boxRag = el("div", { className: "rag-cultura-box stack-sm" }, [
    el("span", { className: "small muted", text: "Carregando Cultura (RAG)..." }),
  ]);
  card.appendChild(boxRag);
  carregarCulturaRag(boxRag, contaId);

  const presets = new Set();
  let editarAtual = Boolean(ehImagem && midiaAtual && !midiaAtual.tipo_arquivo.startsWith("video/"));
  if (ehImagem) {
    const chips = PRESETS_MELHORIA.map((p) => {
      const chk = el("input", { type: "checkbox" });
      chk.addEventListener("change", () => { if (chk.checked) presets.add(p.id); else presets.delete(p.id); });
      return el("label", { className: "presets-chip" }, [chk, el("span", { text: p.label })]);
    });
    card.appendChild(el("div", { className: "seletor-presets" }, chips));
    if (midiaAtual && !midiaAtual.tipo_arquivo.startsWith("video/")) {
      const chkEditar = el("input", { type: "checkbox" });
      chkEditar.checked = editarAtual;
      chkEditar.addEventListener("change", () => { editarAtual = chkEditar.checked; });
      card.appendChild(el("label", { className: "check small" }, [
        chkEditar,
        el("span", { text: "Editar a imagem atual (desmarque para gerar uma nova do zero)" }),
      ]));
    }
  }

  const txtCtx = el("textarea", {
    rows: "3",
    placeholder: ehImagem ? "Descreva ajustes visuais ou novo cenário..." : "Ex.: deixe o tom mais urgente, inclua CTA para comentários...",
  });
  card.appendChild(el("label", {}, [el("span", { text: "Contexto adicional para a IA" }), txtCtx]));

  const btnRecriar = el("button", { type: "button", className: "btn-primary", text: "✨ Recriar com IA" });
  const btnCancelar = el("button", { type: "button", className: "btn-ghost", text: "Cancelar" });
  btnCancelar.addEventListener("click", fechar);
  btnRecriar.addEventListener("click", async () => {
    btnRecriar.setAttribute("disabled", "disabled");
    btnRecriar.textContent = "Recriando...";
    try {
      await apiJson(`/posts/${contaId}/${post.id}/recriar`, "POST", {
        alvo,
        contexto_adicional: txtCtx.value.trim(),
        presets_melhoria: [...presets],
        midia_base_id: ehImagem && editarAtual && midiaAtual ? midiaAtual.id : null,
      });
      notificar(`${ehImagem ? "Imagem" : "Legenda"} recriada com Cultura RAG!`);
      fechar();
      await aoConcluir();
    } catch (err) {
      notificar(err.message, "erro");
      btnRecriar.removeAttribute("disabled");
      btnRecriar.textContent = "✨ Recriar com IA";
    }
  });
  card.appendChild(el("div", { className: "row-actions" }, [btnRecriar, btnCancelar]));
}

export function abrirModalTrocarFoto({ post, contaId, aoConcluir }) {
  const { card, fechar } = criarBaseModal("📷 Substituir Foto / Mídia do Card");
  const boxSeletor = el("div", { className: "seletor-midia-box" });
  card.appendChild(boxSeletor);

  const seletor = criarSeletorMidiaIA({
    containerEl: boxSeletor,
    obterContaAtiva: () => contaId,
    multiplo: false,
    permitirModoIA: false,
  });

  const btnAplicar = el("button", { type: "button", className: "btn-primary", text: "✅ Aplicar Foto no Card" });
  const btnCancelar = el("button", { type: "button", className: "btn-ghost", text: "Cancelar" });
  btnCancelar.addEventListener("click", fechar);
  btnAplicar.addEventListener("click", async () => {
    const { midiaIdsSelecionadas } = seletor.obterEstado();
    if (!midiaIdsSelecionadas.length) return notificar("Selecione ou envie uma foto primeiro.", "erro");
    btnAplicar.setAttribute("disabled", "disabled");
    try {
      await apiJson(`/posts/${contaId}/${post.id}/midia`, "PATCH", { nova_midia_id: midiaIdsSelecionadas[0] });
      notificar("Mídia do card atualizada!");
      fechar();
      await aoConcluir();
    } catch (err) {
      notificar(err.message, "erro");
      btnAplicar.removeAttribute("disabled");
    }
  });
  card.appendChild(el("div", { className: "row-actions" }, [btnAplicar, btnCancelar]));
}
