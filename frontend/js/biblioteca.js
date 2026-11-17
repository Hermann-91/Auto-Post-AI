import { apiFetch, apiJson } from "/painel/js/api.js";
import { aplicarCorProgresso } from "/painel/js/componentes/custos_kpi.js";
import { criarEstadoVazio } from "/painel/js/componentes/estado_vazio.js";
import { el, formatarBytes, limpar, notificar } from "/painel/js/dom.js";
import { iconeTexto } from "/painel/js/icones.js";

let pastaAtiva = "";

function criarCardMidia(item, contaId, recarregar) {
  const srcPreview = `/biblioteca/${contaId}/midias/${item.id}/conteudo`;
  const ehVideo = item.tipo_arquivo.startsWith("video/");
  const thumb = ehVideo
    ? el("video", { className: "media-thumb", src: srcPreview, controls: "true" })
    : el("img", { className: "media-thumb", src: srcPreview, alt: item.pasta, loading: "lazy" });

  const previewBox = el("div", { className: "media-preview-box" }, [
    thumb,
    el("span", { className: "badge media-badge-pasta", text: item.pasta }),
  ]);

  const btnCurtir = el("button", {
    type: "button",
    className: `${item.curtida_favorita ? "btn-primary" : "btn-outline"} btn-sm btn-inline-icone`,
  }, iconeTexto("heart", item.curtida_favorita ? "Favorita" : "Curtir", { tamanho: 13, preenchido: item.curtida_favorita }));
  btnCurtir.addEventListener("click", async () => {
    btnCurtir.setAttribute("disabled", "disabled");
    try {
      await apiJson(`/biblioteca/${contaId}/${item.id}/curtida`, "PATCH", { favorita: !item.curtida_favorita });
      await recarregar();
    } catch (err) {
      notificar(err.message, "erro");
      btnCurtir.removeAttribute("disabled");
    }
  });

  const btnCurar = el("button", {
    type: "button", className: "btn-ghost btn-sm btn-inline-icone",
  }, iconeTexto("sparkles", "IA Descrever", { tamanho: 13 }));
  btnCurar.addEventListener("click", async () => {
    btnCurar.setAttribute("disabled", "disabled");
    try {
      const res = await apiFetch(`/ia/curadoria/${contaId}/${item.id}`, { method: "POST" });
      notificar(`Curadoria salva ($${res.custo_usd})`);
      await recarregar();
    } catch (err) {
      notificar(err.message, "erro");
      btnCurar.removeAttribute("disabled");
    }
  });

  const btnExcluir = el("button", {
    type: "button", className: "btn-danger-outline btn-sm btn-inline-icone",
  }, iconeTexto("trash", "Excluir", { tamanho: 13 }));
  btnExcluir.addEventListener("click", async () => {
    if (!window.confirm("Excluir permanentemente esta mídia da Biblioteca?")) return;
    btnExcluir.setAttribute("disabled", "disabled");
    try {
      const res = await apiFetch(`/biblioteca/${contaId}/${item.id}`, { method: "DELETE" });
      notificar(`Mídia excluída (${formatarBytes(res.bytes_liberados)} liberados).`);
      await recarregar();
    } catch (err) {
      notificar(err.message, "erro");
      btnExcluir.removeAttribute("disabled");
    }
  });

  const resumo = item.resumo_visual || item.chave_storage.split("/").pop();
  return el("article", { className: "media-item" }, [
    previewBox,
    el("div", { className: "media-body" }, [
      el("div", { className: "row-between" }, [
        el("span", { className: "small muted", text: ehVideo ? "Vídeo" : "Imagem" }),
        el("span", { className: "small muted", text: formatarBytes(item.tamanho_bytes) }),
      ]),
      el("p", { className: "small muted media-resumo", text: resumo, title: resumo }),
      el("div", { className: "media-acoes" }, [btnCurtir, btnCurar, btnExcluir]),
    ]),
  ]);
}

export async function carregarBiblioteca(contaId) {
  if (!contaId) return;
  const query = pastaAtiva ? `?pasta=${encodeURIComponent(pastaAtiva)}` : "";
  const [cota, itens] = await Promise.all([
    apiFetch(`/biblioteca/${contaId}/cota`),
    apiFetch(`/biblioteca/${contaId}${query}`),
  ]);

  const pctMax = Math.max(cota.percentual_itens, cota.percentual_bytes);
  aplicarCorProgresso(document.getElementById("cota-itens-bar"), pctMax);
  const txt = document.getElementById("cota-texto");
  if (txt) {
    txt.textContent = `${cota.itens_usados}/${cota.max_itens} mídias (${cota.percentual_itens}%) • ${formatarBytes(cota.bytes_usados)} / ${formatarBytes(cota.max_bytes)}`;
  }

  const grid = document.getElementById("grid-midias");
  if (!grid) return;
  limpar(grid);
  if (!itens.length) {
    grid.appendChild(criarEstadoVazio({
      icone: "image",
      titulo: pastaAtiva ? `Nenhuma mídia na pasta "${pastaAtiva}".` : "Sua Biblioteca ainda está vazia.",
      descricao: pastaAtiva
        ? "Envie um arquivo para esta pasta ou volte para Todas para ver as demais mídias."
        : "Envie fotos ou vídeos no card acima para usar em posts manuais, edições e grades IA.",
      acaoLabel: pastaAtiva ? "Ver todas as pastas" : "Selecionar arquivo",
      acaoIcone: pastaAtiva ? "layers" : "upload",
      aoAcionar: () => {
        if (pastaAtiva) document.querySelector("#filtro-pastas button[data-pasta='']")?.click();
        else document.getElementById("upload-arquivo")?.focus();
      },
      classeExtra: "agenda-empty-state",
    }));
    return;
  }
  for (const item of itens) grid.appendChild(criarCardMidia(item, contaId, () => carregarBiblioteca(contaId)));
}

export function inicializarBiblioteca(obterContaAtiva) {
  const btnRecarregar = document.getElementById("btn-recarregar-bib");
  if (btnRecarregar) {
    limpar(btnRecarregar);
    btnRecarregar.classList.add("btn-inline-icone", "btn-sm");
    btnRecarregar.append(...iconeTexto("refresh", "Atualizar", { tamanho: 14 }));
    btnRecarregar.addEventListener("click", () => carregarBiblioteca(obterContaAtiva()));
  }

  document.getElementById("filtro-pastas")?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-pasta]");
    if (!btn) return;
    pastaAtiva = btn.getAttribute("data-pasta") || "";
    document.querySelectorAll("#filtro-pastas .tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    carregarBiblioteca(obterContaAtiva());
  });

  document.getElementById("form-upload")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const fd = new FormData(e.target);
    try {
      await apiFetch(`/biblioteca/${contaId}/upload`, { method: "POST", body: fd });
      notificar("Mídia enviada com sucesso.");
      e.target.reset();
      await carregarBiblioteca(contaId);
    } catch (err) {
      notificar(err.message, "erro");
    }
  });

  document.getElementById("btn-limpar-pos")?.addEventListener("click", async () => {
    const contaId = obterContaAtiva();
    if (!contaId) return;
    try {
      const res = await apiFetch(`/biblioteca/${contaId}/limpar-pos-postagem`, { method: "POST" });
      notificar(`Limpeza concluída: ${res.removidas_qtd} removida(s), ${formatarBytes(res.bytes_liberados)} liberados.`);
      await carregarBiblioteca(contaId);
    } catch (err) {
      notificar(err.message, "erro");
    }
  });
}
