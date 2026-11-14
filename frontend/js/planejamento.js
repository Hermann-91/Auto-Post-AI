import { apiFetch, apiJson } from "/painel/js/api.js";
import { carregarBiblioteca } from "/painel/js/biblioteca.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

function criarCardPlano(plano, contaId, postsPlano, midiaPorChave, recarregar) {
  const acoes = [];
  if (plano.status === "AGUARDANDO_APROVACAO") {
    const btnAprovar = el("button", { type: "button", className: "btn-primary", text: "Etapa 2a: Aprovar Orçamento" });
    btnAprovar.addEventListener("click", async () => {
      try {
        await apiFetch(`/planejamento/${contaId}/${plano.id}/aprovar`, { method: "POST" });
        notificar("Plano aprovado.");
        await recarregar();
      } catch (err) { notificar(err.message, "erro"); }
    });
    acoes.push(btnAprovar);
  }
  if (["APROVADO", "CONCLUIDO", "FALHA"].includes(plano.status)) {
    const txtBtn = plano.status === "APROVADO" ? "Etapa 2b: Executar & Gerar Fotos" : "🔄 Gerar Fotos & Rascunhos da Semana";
    const btnExec = el("button", { type: "button", className: "btn-primary", text: txtBtn });
    btnExec.addEventListener("click", async () => {
      try {
        const res = await apiFetch(`/planejamento/${contaId}/${plano.id}/executar`, { method: "POST" });
        notificar(`Executado! ${res.postagens_criadas.length} post(s) criado(s) ($${res.custo_real_usd}).`);
        await recarregar();
        await carregarBiblioteca(contaId);
      } catch (err) { notificar(err.message, "erro"); }
    });
    acoes.push(btnExec);
  }

  const thumbsPlano = postsPlano.map((pt) => {
    const m = (pt.midias_chaves || []).map((c) => midiaPorChave.get(c)).find(Boolean);
    if (!m) return null;
    const url = `/biblioteca/${contaId}/midias/${m.id}/conteudo`;
    return el("a", { href: url, target: "_blank", className: "plano-mini-card" }, [
      el("img", { src: url, className: "plano-mini-img", alt: "Arte" }),
      el("span", { className: "small", text: `${(pt.legenda || "").slice(0, 42)}...` }),
    ]);
  }).filter(Boolean);

  const itensEl = (plano.itens_grade || []).map((it) =>
    el("li", { className: "small muted", text: `${it.dia_semana || ""} [${it.formato || "IMAGE"}] ${it.tema || ""} — 🎨 ${it.ideia_visual || ""}` })
  );
  return el("div", { className: "item-card stack-sm" }, [
    el("div", { className: "row-between" }, [
      el("strong", { text: `Semana ${plano.semana_inicio} • Est. $${plano.custo_estimado_usd} USD` }),
      el("span", { className: "badge", text: plano.status }),
    ]),
    el("ul", {}, itensEl),
    thumbsPlano.length ? el("div", { className: "plano-thumbs-grid" }, thumbsPlano) : null,
    el("div", { className: "row-actions" }, acoes),
  ]);
}

function montarColunaMidiaPost(post, contaId, midiaPorChave) {
  const midias = (post.midias_chaves || []).map((ch) => midiaPorChave.get(ch)).filter(Boolean);
  if (!midias.length) {
    return el("div", { className: "post-thumb-col" }, [el("div", { className: "post-thumb-placeholder small muted", text: "Sem mídia" })]);
  }
  const principal = midias[0];
  const url = `/biblioteca/${contaId}/midias/${principal.id}/conteudo`;
  const preview = principal.tipo_arquivo.startsWith("video/")
    ? el("video", { className: "post-thumb-img", src: url, controls: "true" })
    : el("img", { className: "post-thumb-img", src: url, alt: post.tipo_midia, loading: "lazy" });
  const seloPostado = post.status === "PUBLICADO"
    ? el("span", { className: "badge badge-ok", text: "✅ Já Postado no IG" })
    : null;
  const linkAbrir = el("a", { href: url, target: "_blank", rel: "noopener noreferrer", className: "small post-thumb-link", text: `🔍 Ver Arte (${principal.pasta})` });
  return el("div", { className: "post-thumb-col" }, [preview, seloPostado, linkAbrir]);
}

function criarCardPost(post, contaId, midiaPorChave, recarregar) {
  const midias = (post.midias_chaves || []).map((ch) => midiaPorChave.get(ch)).filter(Boolean);
  const promptVisual = midias.map((m) => m.resumo_visual).find(Boolean) || "";
  const jaPostado = post.status === "PUBLICADO";
  const acoes = [];
  if (["RASCUNHO", "AGENDADO", "FALHA", "PUBLICADO"].includes(post.status)) {
    const inputData = el("input", { type: "datetime-local" });
    const btnAg = el("button", { type: "button", className: "btn-outline", text: jaPostado ? "Agendar Repost" : "Agendar" });
    btnAg.addEventListener("click", async () => {
      if (!inputData.value) return notificar("Escolha data e hora.", "erro");
      try {
        await apiJson(`/posts/${contaId}/${post.id}/agendar`, "POST", { agendado_para: new Date(inputData.value).toISOString() });
        notificar("Postagem agendada.");
        await recarregar();
      } catch (err) { notificar(err.message, "erro"); }
    });
    const btnPub = el("button", { type: "button", className: "btn-primary", text: jaPostado ? "🔄 Repostar Agora" : "Publicar Agora" });
    btnPub.addEventListener("click", async () => {
      try {
        const r = await apiFetch(`/posts/${contaId}/${post.id}/publicar-agora`, { method: "POST" });
        notificar(r.publicada ? (r.motivo || "Publicado no Instagram!") : r.motivo, r.publicada ? "ok" : "erro");
        await recarregar();
      } catch (err) { notificar(err.message, "erro"); }
    });
    acoes.push(inputData, btnAg, btnPub);
    if (!jaPostado) {
      const btnCanc = el("button", { type: "button", className: "btn-danger", text: "Cancelar" });
      btnCanc.addEventListener("click", async () => {
        try {
          await apiFetch(`/posts/${contaId}/${post.id}/cancelar`, { method: "POST" });
          notificar("Postagem cancelada.");
          await recarregar();
        } catch (err) { notificar(err.message, "erro"); }
      });
      acoes.push(btnCanc);
    }
  }

  const colInfo = el("div", { className: "post-info-col stack-sm" }, [
    el("div", { className: "row-between" }, [
      el("strong", { text: `${post.tipo_midia} • Postagem Gerada` }),
      el("span", { className: jaPostado ? "badge badge-ok" : "badge", text: jaPostado ? "✅ POSTADO" : post.status }),
    ]),
    el("div", { className: "post-texto-box" }, [
      el("span", { className: "small muted", text: "📝 Legenda & Hashtags:" }),
      el("p", { className: "post-legenda-txt", text: post.legenda || "(Stories sem legenda)" }),
    ]),
    promptVisual ? el("div", { className: "post-prompt-box" }, [
      el("span", { className: "small muted", text: "🎨 Prompt Gerado para a Imagem:" }),
      el("p", { className: "small", text: promptVisual }),
    ]) : null,
    post.meta_media_id ? el("p", { className: "small", text: `✓ ID Publicação: ${post.meta_media_id}` }) : null,
    post.erro_detalhe ? el("p", { className: "small muted", text: `Detalhe: ${post.erro_detalhe}` }) : null,
    el("div", { className: "row-actions" }, acoes),
  ]);

  return el("div", { className: "item-card post-card-visual" }, [
    montarColunaMidiaPost(post, contaId, midiaPorChave),
    colInfo,
  ]);
}

export async function carregarPlanejamentoEPosts(contaId) {
  if (!contaId) return;
  const [planos, posts, midias] = await Promise.all([
    apiFetch(`/planejamento/${contaId}`),
    apiFetch(`/posts/${contaId}`),
    apiFetch(`/biblioteca/${contaId}`),
  ]);
  const midiaPorChave = new Map((midias || []).map((m) => [m.chave_storage, m]));
  const boxPlanos = document.getElementById("lista-planos");
  const boxPosts = document.getElementById("lista-posts");
  if (boxPlanos) {
    limpar(boxPlanos);
    if (!planos.length) boxPlanos.appendChild(el("p", { className: "muted", text: "Nenhum planejamento criado ainda." }));
    for (const p of planos) {
      const postsPlano = posts.filter((pt) => pt.planejamento_id === p.id);
      boxPlanos.appendChild(criarCardPlano(p, contaId, postsPlano, midiaPorChave, () => carregarPlanejamentoEPosts(contaId)));
    }
  }
  if (boxPosts) {
    limpar(boxPosts);
    if (!posts.length) boxPosts.appendChild(el("p", { className: "muted", text: "Nenhuma postagem encontrada." }));
    for (const post of posts) boxPosts.appendChild(criarCardPost(post, contaId, midiaPorChave, () => carregarPlanejamentoEPosts(contaId)));
  }
}

export function inicializarPlanejamento(obterContaAtiva) {
  document.getElementById("btn-recarregar-planos")?.addEventListener("click", () => carregarPlanejamentoEPosts(obterContaAtiva()));
  document.getElementById("btn-recarregar-posts")?.addEventListener("click", () => carregarPlanejamentoEPosts(obterContaAtiva()));

  document.getElementById("form-propor-plano")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const fd = new FormData(e.target);
    try {
      const p = await apiJson("/planejamento/propor", "POST", {
        conta_ig_id: contaId, semana_inicio: String(fd.get("semana_inicio")),
        quantidade_posts: Number(fd.get("quantidade_posts") || 5),
        nicho: String(fd.get("nicho") || ""), regiao: String(fd.get("regiao") || ""),
        objetivo_semana: String(fd.get("objetivo_semana") || ""), incluir_imagens_ia: Boolean(fd.get("incluir_imagens_ia")),
      });
      notificar(`Grade proposta! Custo estimado: $${p.custo_estimado_usd} USD.`);
      await carregarPlanejamentoEPosts(contaId);
    } catch (err) { notificar(err.message, "erro"); }
  });

  document.getElementById("form-criar-ia")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const fd = new FormData(e.target);
    try {
      const res = await apiJson("/ia/criar", "POST", {
        conta_ig_id: contaId, tipo_midia: String(fd.get("tipo_midia") || "IMAGE"),
        tema: String(fd.get("tema") || ""), gerar_imagem_ia: Boolean(fd.get("gerar_imagem_ia")),
      });
      notificar(`Rascunho criado ($${res.custo_total_usd} USD).`);
      e.target.reset();
      await carregarPlanejamentoEPosts(contaId);
      await carregarBiblioteca(contaId);
    } catch (err) { notificar(err.message, "erro"); }
  });
}
