import { apiFetch, apiJson, executarJobIA } from "/painel/js/api.js";
import { criarSeletorMidiaIA, PRESETS_MELHORIA } from "/painel/js/componentes/seletor_midia_ia.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

const RAPIDOS_MODAL = [
  ["Mais natural", "Deixar a fotografia mais natural e documental, sem aspecto artificial."],
  ["Sem pessoas", "Remover pessoas da cena mantendo o foco no ambiente e nos objetos."],
  ["Trocar ângulo", "Recriar a foto com outro ângulo e enquadramento distinto."],
];

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
  const executarRecriacao = async (ctxManual = null) => {
    btnRecriar.setAttribute("disabled", "disabled");
    btnRecriar.textContent = "Recriando...";
    try {
      await executarJobIA({
        contaId, tipoJob: "RECRIAR_POSTAGEM", chaveIdempotencia: `mod-${post.id}-${alvo}-${Date.now()}`,
        payload: {
          recriar_postagem: {
            postagem_id: post.id, alvo,
            contexto_adicional: (ctxManual ?? txtCtx.value).trim(),
            presets_melhoria: [...presets],
            midia_base_id: ehImagem && editarAtual && midiaAtual ? midiaAtual.id : null,
          },
        },
      });
      notificar(`${ehImagem ? "Imagem" : "Legenda"} recriada com Cultura RAG!`);
      fechar();
      await aoConcluir();
    } catch (err) {
      notificar(err.message, "erro");
      btnRecriar.removeAttribute("disabled");
      btnRecriar.textContent = "✨ Recriar com IA";
    }
  };
  if (ehImagem) {
    const barraRapidos = el("div", { className: "row-actions" }, RAPIDOS_MODAL.map(([lbl, ctx]) => {
      const b = el("button", { type: "button", className: "btn-outline btn-sm", text: lbl });
      b.addEventListener("click", () => executarRecriacao(ctx));
      return b;
    }));
    card.appendChild(barraRapidos);
  }
  btnRecriar.addEventListener("click", () => executarRecriacao());
  card.appendChild(el("div", { className: "row-actions" }, [btnRecriar, btnCancelar]));
}

export function abrirModalTrocarFoto({ post, contaId, aoConcluir }) {
  const { card, fechar } = criarBaseModal("📷 Substituir Foto / Mídia do Card");
  const boxSeletor = el("div", { className: "seletor-midia-box" });
  card.appendChild(boxSeletor);
  const ehCarrossel = post.tipo_midia === "CAROUSEL";

  const seletor = criarSeletorMidiaIA({
    containerEl: boxSeletor,
    obterContaAtiva: () => contaId,
    multiplo: ehCarrossel,
    permitirModoIA: false,
  });

  const btnAplicar = el("button", { type: "button", className: "btn-primary", text: "✅ Aplicar Foto no Card" });
  const btnCancelar = el("button", { type: "button", className: "btn-ghost", text: "Cancelar" });
  btnCancelar.addEventListener("click", fechar);
  btnAplicar.addEventListener("click", async () => {
    const { midiaIdsSelecionadas } = seletor.obterEstado();
    if (!midiaIdsSelecionadas.length) return notificar("Selecione ou envie uma foto primeiro.", "erro");
    if (ehCarrossel && midiaIdsSelecionadas.length < 2) return notificar("Carrossel exige entre 2 e 10 mídias.", "erro");
    btnAplicar.setAttribute("disabled", "disabled");
    try {
      await apiJson(`/posts/${contaId}/${post.id}/midias`, "PATCH", { midia_ids: midiaIdsSelecionadas });
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
