import { apiFetch, apiJson } from "/painel/js/api.js";
import { carregarBiblioteca } from "/painel/js/biblioteca.js";
import { criarCardAgenda } from "/painel/js/componentes/card_agenda.js";
import { renderizarPreviaUnitaria, renderizarResumoSemanal } from "/painel/js/componentes/resumo_orcamento.js";
import { criarSeletorMidiaIA } from "/painel/js/componentes/seletor_midia_ia.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

let seletorSemanal = null, seletorUnitario = null, planoSelecionadoId = "", previaUnitaria = null, ultimaContaId = "";

function atualizarPrevia(contaId) {
  renderizarPreviaUnitaria({
    container: document.getElementById("previa-unitaria-box"),
    previa: previaUnitaria,
    contaId,
    aoLimpar: () => { previaUnitaria = null; atualizarPrevia(contaId); },
    aoConcluir: async () => { previaUnitaria = null; seletorUnitario?.limparSelecao(); await carregarPlanejamentoEPosts(contaId); },
  });
}

function montarPayloadUnitario(fd, est, contaId) {
  const tipoConteudo = String(fd.get("tipo_conteudo") || "imagem");
  let tipoMidia = String(fd.get("posicionamento") || "IMAGE");
  if (tipoConteudo === "video" && tipoMidia === "IMAGE") tipoMidia = "REELS";
  const ehReels = tipoMidia === "REELS" || tipoConteudo === "video";
  const ehTexto = tipoConteudo === "texto";
  const temAnexo = est.midiaIdsSelecionadas.length > 0;
  const editarAnexo = !ehReels && !ehTexto && temAnexo && (est.presetsMelhoria.length > 0 || Boolean(est.promptExtra));
  return {
    tipoMidia,
    erro: !ehTexto && est.modo !== "ia" && !temAnexo ? "Anexe/selecione uma mídia ou escolha 'Criar do Zero (IA)'." : "",
    payload: {
      conta_ig_id: contaId, tipo_midia: tipoMidia, tema: String(fd.get("tema") || ""),
      gerar_imagem_ia: !ehReels && !ehTexto && est.modo === "ia",
      editar_midia_id: editarAnexo ? est.midiaIdsSelecionadas[0] : null,
      midia_base_ids: editarAnexo ? [] : est.midiaIdsSelecionadas,
      prompt_visual_extra: est.promptExtra, presets_melhoria: est.presetsMelhoria,
      proporcao: tipoMidia === "STORIES" || tipoMidia === "REELS" ? "9:16" : "4:5",
      aplicar_logo: est.aplicarLogo, salvar_rascunho: false,
    },
  };
}

export async function carregarPlanejamentoEPosts(contaId) {
  if (!contaId) return;
  if (ultimaContaId && ultimaContaId !== contaId) {
    planoSelecionadoId = "";
    previaUnitaria = null;
    seletorSemanal?.limparSelecao();
    seletorUnitario?.limparSelecao();
  }
  ultimaContaId = contaId;

  const [planos, posts, midias] = await Promise.all([
    apiFetch(`/planejamento/${contaId}`),
    apiFetch(`/posts/${contaId}`),
    apiFetch(`/biblioteca/${contaId}`),
  ]);
  const midiaPorChave = new Map((midias || []).map((m) => [m.chave_storage, m]));
  const midiaPorId = new Map((midias || []).map((m) => [m.id, m]));

  renderizarResumoSemanal({
    container: document.getElementById("resumo-semanal-box"), planos: planos || [], contaId, midiaPorId, planoSelecionadoId,
    aoAtualizar: async (id) => { planoSelecionadoId = id || ""; await carregarPlanejamentoEPosts(contaId); await carregarBiblioteca(contaId); },
  });
  atualizarPrevia(contaId);

  const boxPosts = document.getElementById("lista-posts");
  if (boxPosts) {
    limpar(boxPosts);
    const ativos = (posts || []).filter((p) => p.status !== "CANCELADO");
    if (!ativos.length) return boxPosts.appendChild(el("p", { className: "muted", text: "Nenhuma postagem na Agenda." }));
    for (const post of ativos) boxPosts.appendChild(criarCardAgenda(post, contaId, midiaPorChave, () => carregarPlanejamentoEPosts(contaId)));
  }
}

export function inicializarPlanejamento(obterContaAtiva) {
  seletorSemanal = criarSeletorMidiaIA({ idContainer: "seletor-midia-semanal", obterContaAtiva, multiplo: true, permitirModoIA: true });
  seletorUnitario = criarSeletorMidiaIA({ idContainer: "seletor-midia-unitario", obterContaAtiva, multiplo: false, permitirModoIA: true, mostrarLogo: true });
  const atualizarRestricao = () => {
    const tipo = document.getElementById("unit-tipo")?.value || "imagem", pos = document.getElementById("unit-posicionamento")?.value || "IMAGE";
    const ehVideo = tipo === "video" || pos === "REELS";
    seletorUnitario?.definirRestricao({ bloquearIA: ehVideo || tipo === "texto", aceitar: ehVideo ? "video/mp4,video/quicktime" : "image/jpeg,image/png,image/webp" });
  };
  document.getElementById("unit-tipo")?.addEventListener("change", atualizarRestricao);
  document.getElementById("unit-posicionamento")?.addEventListener("change", atualizarRestricao);
  document.getElementById("btn-recarregar-posts")?.addEventListener("click", () => carregarPlanejamentoEPosts(obterContaAtiva()));

  document.getElementById("form-propor-plano")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const fd = new FormData(e.target);
    const est = seletorSemanal?.obterEstado() || { midiaIdsSelecionadas: [], presetsMelhoria: [], promptExtra: "" };
    try {
      const p = await apiJson("/planejamento/propor", "POST", {
        conta_ig_id: contaId, semana_inicio: String(fd.get("semana_inicio")),
        quantidade_posts: Number(fd.get("quantidade_posts") || 5),
        nicho: String(fd.get("nicho") || ""), regiao: String(fd.get("regiao") || ""),
        objetivo_semana: String(fd.get("objetivo_semana") || ""), incluir_imagens_ia: Boolean(fd.get("incluir_imagens_ia")),
        midia_ids_anexadas: est.midiaIdsSelecionadas, presets_melhoria: est.presetsMelhoria, instrucao_melhoria: est.promptExtra,
      });
      planoSelecionadoId = p.id;
      notificar(`Grade proposta! Custo estimado: $${p.custo_estimado_usd} USD.`);
      await carregarPlanejamentoEPosts(contaId);
    } catch (err) { notificar(err.message, "erro"); }
  });

  document.getElementById("form-criar-ia")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const est = seletorUnitario?.obterEstado() || { modo: "ia", midiaIdsSelecionadas: [], midiasSelecionadas: [], presetsMelhoria: [], promptExtra: "", aplicarLogo: false };
    const { tipoMidia, erro, payload } = montarPayloadUnitario(new FormData(e.target), est, contaId);
    if (erro) return notificar(erro, "erro");
    try {
      const resultado = await apiJson("/ia/criar", "POST", payload);
      previaUnitaria = { resultado, tipoMidia, midiasBase: est.midiasSelecionadas };
      notificar(`Prévia gerada ($${resultado.custo_total_usd} USD). Revise antes de enviar para a Agenda.`);
      atualizarPrevia(contaId);
      await carregarBiblioteca(contaId);
    } catch (err) { notificar(err.message, "erro"); }
  });
}
