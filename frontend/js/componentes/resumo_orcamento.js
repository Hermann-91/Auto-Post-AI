import { apiJson, executarJobIA } from "/painel/js/api.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

const FORMATOS = ["IMAGE", "CAROUSEL", "REELS", "STORIES"];

function criarLinhaEditavelPlano(item, editavel, contaId, midiaPorId) {
  const formatosSel = el("select", {}, FORMATOS.map((f) => {
    const opt = el("option", { value: f, text: f });
    if (f === (item.formato || "IMAGE")) opt.selected = true;
    return opt;
  }));
  const inpDia = el("input", { type: "text", value: item.dia_semana || "", placeholder: "Dia" });
  const inpHora = el("input", { type: "text", value: item.horario_sugerido || "18:00", placeholder: "18:00" });
  const inpTema = el("input", { type: "text", value: item.tema || "", placeholder: "Tema da publicação" });
  const txtLeg = el("textarea", { rows: "2", placeholder: "Prévia da legenda..." });
  txtLeg.value = item.legenda_previa || "";
  const txtImg = el("textarea", { rows: "2", placeholder: "Prompt da imagem (ideia visual)..." });
  txtImg.value = item.ideia_visual || "";
  const chkIA = el("input", { type: "checkbox" });
  chkIA.checked = Boolean(item.usar_ia_imagem);

  for (const campo of [formatosSel, inpDia, inpHora, inpTema, txtLeg, txtImg, chkIA]) {
    if (!editavel) campo.setAttribute("disabled", "disabled");
  }
  formatosSel.addEventListener("change", () => { item.formato = formatosSel.value; });
  inpDia.addEventListener("input", () => { item.dia_semana = inpDia.value; });
  inpHora.addEventListener("input", () => { item.horario_sugerido = inpHora.value; });
  inpTema.addEventListener("input", () => { item.tema = inpTema.value; });
  txtLeg.addEventListener("input", () => { item.legenda_previa = txtLeg.value; });
  txtImg.addEventListener("input", () => { item.ideia_visual = txtImg.value; });
  chkIA.addEventListener("change", () => {
    item.usar_ia_imagem = chkIA.checked;
    if (!chkIA.checked && item.editar_midia_id) {
      item.midia_base_ids = [item.editar_midia_id];
      item.editar_midia_id = null;
    }
  });

  const anexoId = item.editar_midia_id || (item.midia_base_ids || [])[0];
  const anexo = anexoId ? midiaPorId.get(anexoId) : null;
  const thumb = anexo
    ? el("img", { src: `/biblioteca/${contaId}/midias/${anexo.id}/conteudo`, className: "plano-mini-img", alt: "Anexo" })
    : null;

  return el("div", { className: "resumo-item-card" }, [
    el("div", { className: "resumo-item-topo" }, [inpTema, formatosSel, inpHora]),
    el("div", { className: "row-actions" }, [
      thumb,
      inpDia,
      el("label", { className: "presets-chip" }, [chkIA, el("span", { text: "Imagem IA" })]),
    ]),
    txtLeg,
    txtImg,
  ]);
}

export function renderizarResumoSemanal({ container, planos, contaId, midiaPorId, planoSelecionadoId, aoAtualizar, aoExecutarPlano = null }) {
  if (!container) return;
  limpar(container);
  if (!planos.length) {
    container.appendChild(el("p", { className: "small muted", text: "Gere o planejamento semanal acima para revisar o resumo e o orçamento aqui." }));
    return;
  }

  let plano = planos.find((p) => p.id === planoSelecionadoId) || planos[0];
  if (planos.length > 1) {
    const sel = el("select", {}, planos.map((p) => {
      const opt = el("option", { value: p.id, text: `Semana ${p.semana_inicio} • $${p.custo_estimado_usd} (${p.status})` });
      if (p.id === plano.id) opt.selected = true;
      return opt;
    }));
    sel.addEventListener("change", () =>
      renderizarResumoSemanal({ container, planos, contaId, midiaPorId, planoSelecionadoId: sel.value, aoAtualizar })
    );
    container.appendChild(sel);
  }

  const itensEditados = (plano.itens_grade || []).map((it) => ({ ...it }));
  const editavel = ["AGUARDANDO_APROVACAO", "APROVADO", "RASCUNHO"].includes(plano.status);
  container.appendChild(el("div", { className: "resumo-cabecalho" }, [
    el("strong", { text: `📊 ${itensEditados.length} publicações • Est. $${plano.custo_estimado_usd} USD` }),
    el("span", { className: "badge", text: plano.status }),
  ]));

  const lista = el("div", { className: "stack-sm" }, itensEditados.map((it) => criarLinhaEditavelPlano(it, editavel, contaId, midiaPorId)));
  container.appendChild(lista);

  const dispararExecucao = async (btn) => {
    if (aoExecutarPlano) return aoExecutarPlano(plano, editavel ? itensEditados : null, btn);
    btn.setAttribute("disabled", "disabled");
    try {
      if (editavel) await apiJson(`/planejamento/${contaId}/${plano.id}/itens`, "PATCH", { itens_grade: itensEditados });
      const job = await executarJobIA({ contaId, tipoJob: "EXECUTAR_PLANO", payload: { executar_plano: { plano_id: plano.id } }, chaveIdempotencia: `exec-${plano.id}-${Date.now()}` });
      notificar(`Concluído! ${(job.resultado_json?.postagens_criadas || []).length} post(s) na Agenda.`);
      await aoAtualizar(plano.id);
    } catch (err) { notificar(err.message, "erro"); }
    finally { btn.removeAttribute("disabled"); }
  };
  const acoes = [];
  if (editavel) {
    const btnSalvar = el("button", { type: "button", className: "btn-outline", text: "💾 Salvar Ajustes" });
    btnSalvar.addEventListener("click", async () => {
      try {
        const atual = await apiJson(`/planejamento/${contaId}/${plano.id}/itens`, "PATCH", { itens_grade: itensEditados });
        notificar(`Resumo salvo! Novo orçamento: $${atual.custo_estimado_usd} USD.`);
        await aoAtualizar(plano.id);
      } catch (err) { notificar(err.message, "erro"); }
    });
    const btnConcluir = el("button", { type: "button", className: "btn-primary", text: "✅ Aprovar & Concluir p/ Agenda" });
    btnConcluir.addEventListener("click", () => dispararExecucao(btnConcluir));
    acoes.push(btnSalvar, btnConcluir);
  } else {
    const btnRegerar = el("button", { type: "button", className: "btn-outline", text: "🔄 Gerar Fotos & Rascunhos Novamente" });
    btnRegerar.addEventListener("click", () => dispararExecucao(btnRegerar));
    acoes.push(btnRegerar);
  }
  container.appendChild(el("div", { className: "row-actions" }, acoes));
}

export function renderizarPreviaUnitaria({ container, previa, contaId, aoConcluir, aoLimpar }) {
  if (!container) return;
  limpar(container);
  if (!previa) {
    container.appendChild(el("p", { className: "small muted", text: "O conteúdo ou arte gerada aparecerá aqui para revisão antes de ir para a Agenda." }));
    return;
  }

  const { resultado, tipoMidia, midiasBase = [] } = previa;
  const midiasFinais = resultado.midias_geradas?.length ? resultado.midias_geradas : midiasBase;
  const primeira = midiasFinais[0] || null;
  const url = primeira ? `/biblioteca/${contaId}/midias/${primeira.id}/conteudo` : "";
  const mediaEl = primeira
    ? (primeira.tipo_arquivo.startsWith("video/")
      ? el("video", { src: url, className: "previa-unitaria-img", controls: "true" })
      : el("img", { src: url, className: "previa-unitaria-img", alt: "Prévia gerada" }))
    : el("div", { className: "post-thumb-placeholder small muted", text: "Somente Texto" });

  const textoInicial = [resultado.legenda, (resultado.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
  const txtLegenda = el("textarea", { rows: "5", placeholder: "Edite a legenda final antes de enviar para a Agenda..." });
  txtLegenda.value = textoInicial;

  const btnCopiar = el("button", { type: "button", className: "btn-ghost small", text: "📋 Copiar" });
  btnCopiar.addEventListener("click", async () => {
    await navigator.clipboard?.writeText(txtLegenda.value).catch(() => null);
    notificar("Texto copiado.");
  });

  const btnEnviar = el("button", { type: "button", className: "btn-primary", text: "📅 Concluir e Enviar para Agenda" });
  btnEnviar.addEventListener("click", async () => {
    if (!midiasFinais.length) {
      return notificar("Para enviar à Agenda do Instagram, anexe ou gere uma imagem/vídeo.", "erro");
    }
    try {
      await apiJson("/posts", "POST", {
        conta_ig_id: contaId,
        tipo_midia: tipoMidia,
        midia_ids: midiasFinais.map((m) => m.id),
        legenda: txtLegenda.value.trim(),
      });
      notificar("Postagem adicionada à Agenda!");
      await aoConcluir();
    } catch (err) { notificar(err.message, "erro"); }
  });

  const btnDescartar = el("button", { type: "button", className: "btn-ghost small", text: "Descartar" });
  btnDescartar.addEventListener("click", () => aoLimpar && aoLimpar());

  container.appendChild(el("div", { className: "resumo-cabecalho" }, [
    el("strong", { text: `✨ Prévia (${tipoMidia}) • $${resultado.custo_total_usd} USD` }),
    el("span", { className: "small muted", text: (resultado.modelos_usados || []).join(" + ") }),
  ]));
  container.appendChild(el("div", { className: "previa-unitaria-box" }, [
    mediaEl,
    el("div", { className: "stack-sm" }, [
      txtLegenda,
      resultado.prompt_visual ? el("p", { className: "small muted", text: `🎨 Prompt: ${resultado.prompt_visual}` }) : null,
      el("div", { className: "row-actions" }, [btnEnviar, btnCopiar, btnDescartar]),
    ]),
  ]));
}
