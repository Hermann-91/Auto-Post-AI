import { acompanharJobIA, apiFetch, apiJson, executarJobIA } from "/painel/js/api.js";
import { carregarBiblioteca } from "/painel/js/biblioteca.js";
import { criarCardAgenda } from "/painel/js/componentes/card_agenda.js";
import { criarEstudioUnificado } from "/painel/js/componentes/estudio_unificado.js";
import { renderizarResumoSemanal } from "/painel/js/componentes/resumo_orcamento.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

let estudio = null, planoSelecionadoId = "", ultimaContaId = "", pollCtrl = null;

function renderizarJobStatus(job) {
  const box = document.getElementById("job-status-box");
  if (!box) return;
  if (!job) return box.classList.add("hidden");
  box.classList.remove("hidden");
  limpar(box);
  box.append(
    el("div", { className: "row-between" }, [
      el("strong", { className: "small", text: `⚙️ ${job.tipo_job} • ${job.etapa_atual}` }),
      el("span", { className: "badge", text: `${job.progresso_atual}/${job.progresso_total} (${job.percentual}%)` }),
    ]),
    el("div", { className: "progress-track" }, [
      el("div", { className: "progress-fill", style: `width: ${job.percentual}%` }),
    ])
  );
}

async function executarPlanoComJob(contaId, plano, itensEditados, btn) {
  btn?.setAttribute("disabled", "disabled");
  estudio?.definirOcupado(true);
  try {
    if (itensEditados) await apiJson(`/planejamento/${contaId}/${plano.id}/itens`, "PATCH", { itens_grade: itensEditados });
    const job = await executarJobIA({
      contaId, tipoJob: "EXECUTAR_PLANO",
      payload: { executar_plano: { plano_id: plano.id } },
      chaveIdempotencia: `exec-${plano.id}-${Date.now()}`,
      aoProgredir: renderizarJobStatus, signal: pollCtrl?.signal,
    });
    const criados = job.resultado_json?.postagens_criadas || [];
    notificar(`Lote concluído! ${criados.length} post(s) enviados à Agenda ($${job.resultado_json?.custo_real_usd || "0"} USD).`);
    renderizarJobStatus(null);
    await carregarPlanejamentoEPosts(contaId);
    await carregarBiblioteca(contaId);
  } catch (err) {
    if (err.name !== "AbortError") notificar(err.message, "erro");
    renderizarJobStatus(null);
  } finally {
    btn?.removeAttribute("disabled");
    estudio?.definirOcupado(false);
  }
}

export async function carregarPlanejamentoEPosts(contaId) {
  if (!contaId) return;
  if (ultimaContaId && ultimaContaId !== contaId) {
    pollCtrl?.abort();
    pollCtrl = new AbortController();
    planoSelecionadoId = "";
    renderizarJobStatus(null);
    estudio?.limparMidias();
  }
  if (!pollCtrl) pollCtrl = new AbortController();
  ultimaContaId = contaId;

  const [planos, posts, midias, jobsAtivos] = await Promise.all([
    apiFetch(`/planejamento/${contaId}`), apiFetch(`/posts/${contaId}`),
    apiFetch(`/biblioteca/${contaId}`), apiFetch(`/ia/jobs?conta_ig_id=${contaId}&apenas_ativos=true`),
  ]);
  const midiaPorChave = new Map((midias || []).map((m) => [m.chave_storage, m]));
  const midiaPorId = new Map((midias || []).map((m) => [m.id, m]));

  renderizarResumoSemanal({
    container: document.getElementById("resumo-semanal-box"), planos: planos || [], contaId, midiaPorId, planoSelecionadoId,
    aoSelecionarPlano: (id) => { planoSelecionadoId = id || ""; },
    aoExecutarPlano: (p, itens, btn) => executarPlanoComJob(contaId, p, itens, btn),
    aoAtualizar: async (id) => { planoSelecionadoId = id || ""; await carregarPlanejamentoEPosts(contaId); await carregarBiblioteca(contaId); },
  });

  const boxPosts = document.getElementById("lista-posts");
  if (boxPosts) {
    limpar(boxPosts);
    const ativos = (posts || []).filter((p) => p.status !== "CANCELADO");
    if (!ativos.length) return boxPosts.appendChild(el("p", { className: "muted", text: "Nenhuma postagem na Agenda." }));
    for (const post of ativos) boxPosts.appendChild(criarCardAgenda(post, contaId, midiaPorChave, async () => { await carregarPlanejamentoEPosts(contaId); await carregarBiblioteca(contaId); }));
  }
  if (jobsAtivos?.length) {
    estudio?.definirOcupado(true);
    acompanharJobIA(jobsAtivos[0].id, { aoProgredir: renderizarJobStatus, signal: pollCtrl.signal })
      .then(() => { renderizarJobStatus(null); return carregarPlanejamentoEPosts(contaId); })
      .catch((err) => { if (err.name !== "AbortError") notificar(err.message, "erro"); })
      .finally(() => estudio?.definirOcupado(false));
  }
}

async function enviarManualZero(contaId, dados) {
  const fmt = Object.entries(dados.quantidades).find(([, q]) => q > 0)?.[0] || "IMAGE";
  if (dados.agendarPara && !dados.midiaIds.length) return notificar("Anexe mídia antes de agendar na Meta API.", "erro");
  if (fmt === "CAROUSEL" && dados.midiaIds.length > 0 && dados.midiaIds.length < 2) return notificar("Carrossel exige ao menos 2 mídias.", "erro");
  await apiJson("/posts", "POST", {
    conta_ig_id: contaId, tipo_midia: fmt, midia_ids: dados.midiaIds,
    legenda: fmt === "STORIES" ? "" : dados.tema,
    agendado_para: dados.agendarPara ? new Date(dados.agendarPara).toISOString() : null,
  });
  notificar("Postagem manual adicionada à Agenda ($0.00 USD)!");
  estudio?.limparMidias();
  await carregarPlanejamentoEPosts(contaId);
}

export function inicializarPlanejamento(obterContaAtiva) {
  document.getElementById("btn-recarregar-posts")?.addEventListener("click", () => carregarPlanejamentoEPosts(obterContaAtiva()));
  estudio = criarEstudioUnificado({
    raiz: document.getElementById("estudio-unificado-root"),
    obterContaAtiva,
    aoSubmeter: async (dados) => {
      const contaId = obterContaAtiva();
      if (!contaId) return;
      estudio?.definirOcupado(true);
      try {
        if (dados.modo === "MANUAL_ZERO") return await enviarManualZero(contaId, dados);
        const pilarTxt = dados.pilares.join(", ");
        const fmtUnico = Object.entries(dados.quantidades).find(([, q]) => q > 0)?.[0] || "IMAGE";
        const fuso = Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Sao_Paulo";
        const chave = `${dados.modo}-${Date.now()}`;

        if (dados.total > 1) {
          const obj = [dados.tema, pilarTxt ? `Pilares: ${pilarTxt}` : "", dados.modoSerie ? `Série: ${dados.etapaSerie || "contínua"}` : ""].filter(Boolean).join(" | ") || "crescimento orgânico e autoridade";
          const job = await executarJobIA({
            contaId, tipoJob: "PROPOR_PLANO", chaveIdempotencia: chave,
            aoProgredir: renderizarJobStatus, signal: pollCtrl?.signal,
            payload: { propor_plano: { conta_ig_id: contaId, semana_inicio: dados.semanaInicio, nicho: dados.nicho, regiao: dados.regiao, objetivo_semana: obj, composicao_formatos: dados.quantidades, quantidade_posts: dados.total, incluir_imagens_ia: dados.modo === "IA_COMPLETA", midia_ids_anexadas: dados.midiaIds, presets_melhoria: dados.presetsMelhoria, instrucao_melhoria: dados.promptAvancado || dados.promptExtraVisual, auto_agendar: dados.autoAgendar, fuso_horario: fuso } },
          });
          planoSelecionadoId = job.resultado_json?.id || "";
          notificar(`Grade proposta! Estimado: $${job.resultado_json?.custo_estimado_usd} USD.`);
        } else {
          const editarAnexo = dados.modo === "IA_COMPLETA" && fmtUnico !== "REELS" && dados.midiaIds.length && (dados.presetsMelhoria.length || dados.promptExtraVisual);
          const job = await executarJobIA({
            contaId, tipoJob: "CRIAR_CONTEUDO", chaveIdempotencia: chave,
            aoProgredir: renderizarJobStatus, signal: pollCtrl?.signal,
            payload: { criar_conteudo: { conta_ig_id: contaId, tipo_midia: fmtUnico, tema: dados.tema || pilarTxt || "Conteúdo estratégico da marca", tom_extra: dados.tomExtra, gerar_imagem_ia: dados.modo === "IA_COMPLETA" && fmtUnico !== "REELS" && !editarAnexo, editar_midia_id: editarAnexo ? dados.midiaIds[0] : null, midia_base_ids: editarAnexo ? [] : dados.midiaIds, prompt_visual_extra: dados.promptExtraVisual, presets_melhoria: dados.presetsMelhoria, proporcao: fmtUnico === "STORIES" || fmtUnico === "REELS" ? "9:16" : "4:5", aplicar_logo: dados.aplicarLogo, salvar_rascunho: true, pilar_editorial: pilarTxt, modo_serie: dados.modoSerie, etapa_serie: dados.etapaSerie, prompt_avancado: dados.promptAvancado, agendar_para: dados.agendarPara ? new Date(dados.agendarPara).toISOString() : null } },
          });
          const res = job.resultado_json;
          estudio?.limparMidias();
          notificar(`Salvo direto na Agenda ($${res?.custo_total_usd || "0"} USD)!`);
        }
        renderizarJobStatus(null);
        await carregarPlanejamentoEPosts(contaId);
        await carregarBiblioteca(contaId);
      } catch (err) {
        if (err.name !== "AbortError") notificar(err.message, "erro");
        renderizarJobStatus(null);
      } finally { estudio?.definirOcupado(false); }
    },
  });
}
