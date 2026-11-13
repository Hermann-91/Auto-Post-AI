import { apiFetch, apiJson } from "/painel/js/api.js";
import { el, formatarBytes, limpar, notificar } from "/painel/js/dom.js";

let pastaAtiva = "";

function criarCardMidia(item, contaId, recarregar) {
  const srcPreview = `/biblioteca/${contaId}/midias/${item.id}/conteudo`;
  const ehVideo = item.tipo_arquivo.startsWith("video/");
  const thumb = ehVideo
    ? el("video", { className: "media-thumb", src: srcPreview, controls: "true" })
    : el("img", { className: "media-thumb", src: srcPreview, alt: item.pasta });

  const btnCurtir = el("button", {
    type: "button",
    className: item.curtida_favorita ? "btn-primary" : "btn-outline",
    text: item.curtida_favorita ? "♥ Favorita" : "♡ Curtir",
  });
  btnCurtir.addEventListener("click", async () => {
    try {
      await apiJson(`/biblioteca/${contaId}/${item.id}/curtida`, "PATCH", {
        favorita: !item.curtida_favorita,
      });
      await recarregar();
    } catch (err) {
      notificar(err.message, "erro");
    }
  });

  const btnCurar = el("button", { type: "button", className: "btn-ghost", text: "IA Descrever" });
  btnCurar.addEventListener("click", async () => {
    try {
      const res = await apiFetch(`/ia/curadoria/${contaId}/${item.id}`, { method: "POST" });
      notificar(`Curadoria salva ($${res.custo_usd})`);
      await recarregar();
    } catch (err) {
      notificar(err.message, "erro");
    }
  });

  const resumo = item.resumo_visual || item.chave_storage.split("/").pop();
  return el("article", { className: "media-item" }, [
    thumb,
    el("div", { className: "media-body" }, [
      el("div", { className: "row-between" }, [
        el("span", { className: "badge", text: item.pasta }),
        el("span", { className: "small muted", text: formatarBytes(item.tamanho_bytes) }),
      ]),
      el("p", { className: "small muted", text: resumo }),
      el("div", { className: "row-actions" }, [btnCurtir, btnCurar]),
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

  const bar = document.getElementById("cota-itens-bar");
  const txt = document.getElementById("cota-texto");
  if (bar) bar.style.width = `${Math.min(100, Math.max(cota.percentual_itens, cota.percentual_bytes))}%`;
  if (txt) {
    txt.textContent = `${cota.itens_usados}/${cota.max_itens} mídias (${cota.percentual_itens}%) • ${formatarBytes(cota.bytes_usados)} / ${formatarBytes(cota.max_bytes)}`;
  }

  const grid = document.getElementById("grid-midias");
  if (!grid) return;
  limpar(grid);
  if (!itens.length) {
    grid.appendChild(el("p", { className: "muted", text: "Nenhuma mídia nesta pasta ainda." }));
    return;
  }
  for (const item of itens) grid.appendChild(criarCardMidia(item, contaId, () => carregarBiblioteca(contaId)));
}

export function inicializarBiblioteca(obterContaAtiva) {
  document.getElementById("filtro-pastas")?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-pasta]");
    if (!btn) return;
    pastaAtiva = btn.getAttribute("data-pasta") || "";
    document.querySelectorAll("#filtro-pastas .tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    carregarBiblioteca(obterContaAtiva());
  });

  document.getElementById("btn-recarregar-bib")?.addEventListener("click", () => carregarBiblioteca(obterContaAtiva()));

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
