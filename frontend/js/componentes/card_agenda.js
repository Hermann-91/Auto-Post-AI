import { apiFetch, apiJson, executarJobIA } from "/painel/js/api.js";
import { abrirModalRecriacao, abrirModalTrocarFoto } from "/painel/js/componentes/modal_recriacao.js";
import { el, notificar } from "/painel/js/dom.js";

function paraInputLocal(isoStr) {
  if (!isoStr) return "";
  const dt = new Date(isoStr);
  if (Number.isNaN(dt.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

const ACOES_RAPIDAS = [
  ["Mais natural", "Deixar a fotografia mais natural e documental, sem aspecto artificial."],
  ["Sem pessoas", "Remover pessoas da cena mantendo o foco no ambiente e nos objetos."],
  ["Trocar ângulo", "Recriar a foto com outro ângulo e enquadramento distinto."],
];

export function criarCardAgenda(post, contaId, midiaPorChave, recarregar) {
  const midias = (post.midias_chaves || []).map((ch) => midiaPorChave.get(ch)).filter(Boolean);
  const principal = midias[0] || null;
  const semMidia = !principal && (!post.midias_chaves || !post.midias_chaves.length);
  const promptVisual = midias.map((m) => m.resumo_visual).find(Boolean) || "";
  const jaPostado = post.status === "PUBLICADO";
  const bloqueado = ["PUBLICANDO", "PUBLICADO", "CANCELADO"].includes(post.status);

  const dispararImgRapida = async (btn, contexto, midiaBaseId = null) => {
    btn.setAttribute("disabled", "disabled");
    try {
      await executarJobIA({
        contaId, tipoJob: "RECRIAR_POSTAGEM", chaveIdempotencia: `rap-${post.id}-${btn.textContent}`,
        payload: { recriar_postagem: { postagem_id: post.id, alvo: "imagem", contexto_adicional: contexto, presets_melhoria: [], midia_base_id: midiaBaseId } },
      });
      notificar("Imagem atualizada!");
      await recarregar();
    } catch (err) { notificar(err.message, "erro"); btn.removeAttribute("disabled"); }
  };

  const btnFotoExt = el("button", { type: "button", className: "agenda-btn-foto-ext", text: "📷 Trocar Foto" });
  btnFotoExt.addEventListener("click", () => abrirModalTrocarFoto({ post, contaId, aoConcluir: recarregar }));

  const btnRecriarImg = el("button", {
    type: "button",
    className: "btn-circular-recriar",
    title: "Recriar ou melhorar imagem com IA + Cultura RAG",
    text: "o",
  });
  btnRecriarImg.addEventListener("click", () =>
    abrirModalRecriacao({ post, alvo: "imagem", contaId, midiaAtual: principal, promptAtual: promptVisual, aoConcluir: recarregar })
  );

  const url = principal ? `/biblioteca/${contaId}/midias/${principal.id}/conteudo` : "";
  let midiaEl;
  if (principal) {
    midiaEl = principal.tipo_arquivo.startsWith("video/")
      ? el("video", { className: "agenda-midia-conteudo", src: url, controls: "true" })
      : el("img", { className: "agenda-midia-conteudo", src: url, alt: post.tipo_midia, loading: "lazy" });
  } else {
    const btnAnexar = el("button", { type: "button", className: "btn-outline btn-sm", text: "📷 Anexar Foto" });
    btnAnexar.addEventListener("click", () => abrirModalTrocarFoto({ post, contaId, aoConcluir: recarregar }));
    const acoesVazio = [el("span", { className: "small muted", text: "Rascunho só-texto" }), btnAnexar];
    if (post.tipo_midia !== "REELS") {
      const btnGerarIA = el("button", { type: "button", className: "btn-primary btn-sm", text: "✨ Gerar Imagem IA" });
      btnGerarIA.addEventListener("click", () => dispararImgRapida(btnGerarIA, post.legenda?.slice(0, 300) || "Gerar imagem coerente com a postagem."));
      acoesVazio.splice(1, 0, btnGerarIA);
    }
    midiaEl = el("div", { className: "agenda-sem-midia" }, acoesVazio);
  }
  const controlesMidia = principal ? [midiaEl, btnFotoExt, btnRecriarImg] : [midiaEl];
  const boxMidia = el("div", { className: "agenda-box-midia" }, controlesMidia);

  const btnRecriarTxt = el("button", {
    type: "button",
    className: "btn-circular-recriar",
    title: "Editar manualmente ou recriar legenda com IA",
    text: "o",
  });
  btnRecriarTxt.addEventListener("click", () =>
    abrirModalRecriacao({ post, alvo: "texto", contaId, midiaAtual: principal, promptAtual: promptVisual, aoConcluir: recarregar })
  );

  const agendadoTxt = post.agendado_para ? `⏰ ${new Date(post.agendado_para).toLocaleString("pt-BR")}` : "";
  const boxTexto = el("div", { className: "agenda-box-texto" }, [
    el("div", { className: "row-between" }, [
      el("span", { className: "badge", text: post.tipo_midia }),
      el("span", { className: jaPostado ? "badge badge-ok" : "badge", text: jaPostado ? "✅ POSTADO" : post.status }),
    ]),
    semMidia ? el("span", { className: "badge badge-warn", text: "⏳ Aguardando mídia" }) : null,
    el("p", { className: "agenda-legenda-clamp", text: post.legenda || (post.tipo_midia === "STORIES" ? "(Stories sem legenda)" : "(Sem legenda)"), title: post.legenda || "" }),
    promptVisual ? el("p", { className: "agenda-prompt-mini", text: `🎨 ${promptVisual}`, title: promptVisual }) : null,
    agendadoTxt ? el("span", { className: "small muted", text: agendadoTxt }) : null,
    post.erro_detalhe ? el("span", { className: "small muted", text: `⚠ ${post.erro_detalhe}` }) : null,
    btnRecriarTxt,
  ]);

  const barraRapida = (!semMidia && !bloqueado && principal && !principal.tipo_arquivo.startsWith("video/") && post.tipo_midia !== "REELS")
    ? el("div", { className: "agenda-acoes-rapidas" }, ACOES_RAPIDAS.map(([lbl, ctx]) => {
      const b = el("button", { type: "button", className: "btn-ghost btn-sm", text: lbl });
      b.addEventListener("click", () => dispararImgRapida(b, ctx, principal.id));
      return b;
    }))
    : null;

  const inputData = el("input", { type: "datetime-local", className: "agenda-input-data", value: paraInputLocal(post.agendado_para) });
  const btnAgendar = el("button", { type: "button", className: "btn-outline btn-icone", title: jaPostado ? "Agendar Repost" : "Agendar", text: "📅" });
  btnAgendar.addEventListener("click", async () => {
    if (semMidia) return notificar("Anexe ou gere uma mídia antes de agendar.", "erro");
    if (!inputData.value) return notificar("Escolha data e hora.", "erro");
    try {
      await apiJson(`/posts/${contaId}/${post.id}/agendar`, "POST", { agendado_para: new Date(inputData.value).toISOString() });
      notificar("Postagem agendada!");
      await recarregar();
    } catch (err) { notificar(err.message, "erro"); }
  });

  const btnPostar = el("button", {
    type: "button",
    className: "btn-primary btn-icone",
    text: jaPostado ? "🔄 Repostar" : "Postar Agora",
  });
  btnPostar.addEventListener("click", async () => {
    if (semMidia) return notificar("Anexe ou gere uma mídia antes de publicar.", "erro");
    try {
      const r = await apiFetch(`/posts/${contaId}/${post.id}/publicar-agora`, { method: "POST" });
      notificar(r.publicada ? (r.motivo || "Publicado no Instagram!") : r.motivo, r.publicada ? "ok" : "erro");
      await recarregar();
    } catch (err) { notificar(err.message, "erro"); }
  });

  const btnLixeira = el("button", { type: "button", className: "btn-danger btn-icone", title: "Excluir da Agenda", text: "🗑️" });
  if (post.status === "PUBLICANDO") btnLixeira.setAttribute("disabled", "disabled");
  btnLixeira.addEventListener("click", async () => {
    if (!window.confirm("Excluir este card e suas imagens exclusivas da Agenda?")) return;
    try {
      const r = await apiFetch(`/posts/${contaId}/${post.id}`, { method: "DELETE" });
      const info = r.midias_removidas_qtd ? ` (${r.midias_removidas_qtd} imagem(ns) removida(s))` : "";
      notificar(`Postagem excluída da Agenda${info}.`);
      await recarregar();
    } catch (err) { notificar(err.message, "erro"); }
  });

  if (semMidia) {
    inputData.setAttribute("disabled", "disabled");
    btnAgendar.setAttribute("disabled", "disabled");
    btnPostar.setAttribute("disabled", "disabled");
  }
  const barraAcoes = el("div", { className: "agenda-acoes-barra" }, [inputData, btnAgendar, btnPostar, btnLixeira]);
  return el("article", { className: "agenda-card" }, [boxMidia, boxTexto, barraRapida, barraAcoes]);
}
