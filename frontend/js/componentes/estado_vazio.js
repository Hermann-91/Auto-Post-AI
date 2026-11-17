import { el } from "/painel/js/dom.js";
import { criarIcone, iconeTexto } from "/painel/js/icones.js";

/**
 * Cria um estado vazio padronizado com ícone SVG, descrição acionável e CTA opcional.
 */
export function criarEstadoVazio({
  icone = "sparkles",
  titulo,
  descricao = "",
  acaoLabel = "",
  acaoIcone = "",
  aoAcionar = null,
  classeExtra = "",
}) {
  const filhos = [
    el("span", { className: "empty-state-icone" }, [criarIcone(icone, { tamanho: 26 })]),
    el("strong", { text: titulo }),
    descricao ? el("span", { className: "small muted empty-state-desc", text: descricao }) : null,
  ];
  if (acaoLabel && aoAcionar) {
    const conteudoBtn = acaoIcone ? iconeTexto(acaoIcone, acaoLabel, { tamanho: 14 }) : [acaoLabel];
    const btn = el("button", { type: "button", className: "btn-outline btn-sm btn-inline-icone" }, conteudoBtn);
    btn.addEventListener("click", aoAcionar);
    filhos.push(btn);
  }
  const classe = classeExtra ? `empty-state-box ${classeExtra}` : "empty-state-box";
  return el("div", { className: classe }, filhos);
}
