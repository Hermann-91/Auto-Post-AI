import { apiFetch, apiJson } from "/painel/js/api.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

function criarCardPlano(plano, contaId, recarregar) {
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
  if (plano.status === "APROVADO") {
    const btnExec = el("button", { type: "button", className: "btn-primary", text: "Etapa 2b: Executar & Gerar Rascunhos" });
    btnExec.addEventListener("click", async () => {
      try {
        const res = await apiFetch(`/planejamento/${contaId}/${plano.id}/executar`, { method: "POST" });
        notificar(`Executado! ${res.postagens_criadas.length} post(s) criado(s) ($${res.custo_real_usd}).`);
        await recarregar();
      } catch (err) { notificar(err.message, "erro"); }
    });
    acoes.push(btnExec);
  }

  const itensEl = (plano.itens_grade || []).map((it) =>
    el("li", { className: "small muted", text: `${it.dia_semana || ""} [${it.formato || "IMAGE"}] ${it.tema || ""}` })
  );
  return el("div", { className: "item-card stack-sm" }, [
    el("div", { className: "row-between" }, [
      el("strong", { text: `Semana ${plano.semana_inicio} • Est. $${plano.custo_estimado_usd} USD` }),
      el("span", { className: "badge", text: plano.status }),
    ]),
    el("ul", {}, itensEl),
    el("div", { className: "row-actions" }, acoes),
  ]);
}

function criarCardPost(post, contaId, recarregar) {
  const acoes = [];
  if (["RASCUNHO", "AGENDADO", "FALHA"].includes(post.status)) {
    const inputData = el("input", { type: "datetime-local" });
    const btnAg = el("button", { type: "button", className: "btn-outline", text: "Agendar" });
    btnAg.addEventListener("click", async () => {
      if (!inputData.value) return notificar("Escolha data e hora.", "erro");
      try {
        await apiJson(`/posts/${contaId}/${post.id}/agendar`, "POST", {
          agendado_para: new Date(inputData.value).toISOString(),
        });
        notificar("Postagem agendada.");
        await recarregar();
      } catch (err) { notificar(err.message, "erro"); }
    });
    const btnPub = el("button", { type: "button", className: "btn-primary", text: "Publicar Agora" });
    btnPub.addEventListener("click", async () => {
      try {
        const r = await apiFetch(`/posts/${contaId}/${post.id}/publicar-agora`, { method: "POST" });
        notificar(r.publicada ? "Publicado na Meta!" : r.motivo);
        await recarregar();
      } catch (err) { notificar(err.message, "erro"); }
    });
    const btnCanc = el("button", { type: "button", className: "btn-danger", text: "Cancelar" });
    btnCanc.addEventListener("click", async () => {
      try {
        await apiFetch(`/posts/${contaId}/${post.id}/cancelar`, { method: "POST" });
        notificar("Postagem cancelada.");
        await recarregar();
      } catch (err) { notificar(err.message, "erro"); }
    });
    acoes.push(inputData, btnAg, btnPub, btnCanc);
  }
  return el("div", { className: "item-card stack-sm" }, [
    el("div", { className: "row-between" }, [
      el("strong", { text: `${post.tipo_midia} • ${(post.legenda || "(sem legenda)").slice(0, 80)}` }),
      el("span", { className: "badge", text: post.status }),
    ]),
    post.erro_detalhe ? el("p", { className: "small muted", text: `Detalhe: ${post.erro_detalhe}` }) : null,
    el("div", { className: "row-actions" }, acoes),
  ]);
}

export async function carregarPlanejamentoEPosts(contaId) {
  if (!contaId) return;
  const [planos, posts] = await Promise.all([
    apiFetch(`/planejamento/${contaId}`),
    apiFetch(`/posts/${contaId}`),
  ]);
  const boxPlanos = document.getElementById("lista-planos");
  const boxPosts = document.getElementById("lista-posts");
  if (boxPlanos) {
    limpar(boxPlanos);
    if (!planos.length) boxPlanos.appendChild(el("p", { className: "muted", text: "Nenhum planejamento criado ainda." }));
    for (const p of planos) boxPlanos.appendChild(criarCardPlano(p, contaId, () => carregarPlanejamentoEPosts(contaId)));
  }
  if (boxPosts) {
    limpar(boxPosts);
    if (!posts.length) boxPosts.appendChild(el("p", { className: "muted", text: "Nenhuma postagem encontrada." }));
    for (const post of posts) boxPosts.appendChild(criarCardPost(post, contaId, () => carregarPlanejamentoEPosts(contaId)));
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
        conta_ig_id: contaId,
        semana_inicio: String(fd.get("semana_inicio")),
        quantidade_posts: Number(fd.get("quantidade_posts") || 5),
        nicho: String(fd.get("nicho") || ""),
        regiao: String(fd.get("regiao") || ""),
        objetivo_semana: String(fd.get("objetivo_semana") || ""),
        incluir_imagens_ia: Boolean(fd.get("incluir_imagens_ia")),
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
        conta_ig_id: contaId,
        tipo_midia: String(fd.get("tipo_midia") || "IMAGE"),
        tema: String(fd.get("tema") || ""),
        gerar_imagem_ia: Boolean(fd.get("gerar_imagem_ia")),
      });
      notificar(`Rascunho criado ($${res.custo_total_usd} USD).`);
      e.target.reset();
      await carregarPlanejamentoEPosts(contaId);
    } catch (err) { notificar(err.message, "erro"); }
  });
}
