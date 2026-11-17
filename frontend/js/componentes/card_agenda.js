import { apiFetch, apiJson } from "/painel/js/api.js";
import { abrirModalRecriacao, abrirModalTrocarFoto } from "/painel/js/componentes/modal_recriacao.js";
import { el, notificar } from "/painel/js/dom.js";

function paraInputLocal(isoStr) {
  if (!isoStr) return "";
  const dt = new Date(isoStr);
  if (Number.isNaN(dt.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

export function criarCardAgenda(post, contaId, midiaPorChave, recarregar) {
  const midias = (post.midias_chaves || []).map((ch) => midiaPorChave.get(ch)).filter(Boolean);
  const principal = midias[0] || null;
  const promptVisual = midias.map((m) => m.resumo_visual).find(Boolean) || "";
  const jaPostado = post.status === "PUBLICADO";

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
  const midiaEl = principal
    ? (principal.tipo_arquivo.startsWith("video/")
      ? el("video", { className: "agenda-midia-conteudo", src: url, controls: "true" })
      : el("img", { className: "agenda-midia-conteudo", src: url, alt: post.tipo_midia, loading: "lazy" }))
    : el("div", { className: "post-thumb-placeholder small muted", text: "Sem mídia" });

  const boxMidia = el("div", { className: "agenda-box-midia" }, [midiaEl, btnFotoExt, btnRecriarImg]);

  const btnRecriarTxt = el("button", {
    type: "button",
    className: "btn-circular-recriar",
    title: "Recriar texto/legenda com IA + Cultura RAG",
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
    el("p", { className: "agenda-legenda-clamp", text: post.legenda || "(Stories sem legenda)", title: post.legenda || "" }),
    promptVisual ? el("p", { className: "agenda-prompt-mini", text: `🎨 ${promptVisual}`, title: promptVisual }) : null,
    agendadoTxt ? el("span", { className: "small muted", text: agendadoTxt }) : null,
    post.erro_detalhe ? el("span", { className: "small muted", text: `⚠ ${post.erro_detalhe}` }) : null,
    btnRecriarTxt,
  ]);

  const inputData = el("input", { type: "datetime-local", className: "agenda-input-data", value: paraInputLocal(post.agendado_para) });
  const btnAgendar = el("button", { type: "button", className: "btn-outline btn-icone", title: jaPostado ? "Agendar Repost" : "Agendar", text: "📅" });
  btnAgendar.addEventListener("click", async () => {
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

  const barraAcoes = el("div", { className: "agenda-acoes-barra" }, [inputData, btnAgendar, btnPostar, btnLixeira]);
  return el("article", { className: "agenda-card" }, [boxMidia, boxTexto, barraAcoes]);
}
