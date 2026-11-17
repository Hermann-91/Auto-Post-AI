import { criarEstadoVazio } from "/painel/js/componentes/estado_vazio.js";
import { el, limpar } from "/painel/js/dom.js";

export const FILTROS_AGENDA = [
  { id: "TODOS", rotulo: "Todos", fn: () => true, fixo: true },
  { id: "RASCUNHO", rotulo: "Rascunhos", fn: (p) => p.status === "RASCUNHO", fixo: true },
  { id: "SEM_MIDIA", rotulo: "Aguardando Mídia", fn: (p) => !(p.midias_chaves || []).length, fixo: true },
  { id: "AGENDADO", rotulo: "Agendados", fn: (p) => ["AGENDADO", "PUBLICANDO"].includes(p.status), fixo: true },
  { id: "PUBLICADO", rotulo: "Publicados", fn: (p) => p.status === "PUBLICADO", fixo: true },
  { id: "FALHA", rotulo: "Falhas", fn: (p) => p.status === "FALHA", fixo: false },
];

export function renderizarFiltrosAgenda({ container, ativos, filtroAtivo, aoTrocar }) {
  const contagens = new Map(FILTROS_AGENDA.map((f) => [f.id, ativos.filter(f.fn).length]));
  const visiveis = FILTROS_AGENDA.filter((f) => f.fixo || contagens.get(f.id) > 0);
  const selecionado = visiveis.some((f) => f.id === filtroAtivo) ? filtroAtivo : "TODOS";
  if (!container) return selecionado;

  limpar(container);
  for (const f of visiveis) {
    const ativo = f.id === selecionado;
    const btn = el("button", {
      type: "button",
      className: `agenda-filtro-btn${ativo ? " active" : ""}`,
      role: "tab",
      "aria-selected": String(ativo),
      text: `${f.rotulo} (${contagens.get(f.id) || 0})`,
    });
    btn.addEventListener("click", () => aoTrocar(f.id));
    container.appendChild(btn);
  }
  return selecionado;
}

export function filtrarPostsAgenda(ativos, filtroId) {
  const regra = FILTROS_AGENDA.find((f) => f.id === filtroId) || FILTROS_AGENDA[0];
  return ativos.filter(regra.fn);
}

export function criarEstadoVazioAgenda({ temAtivos, aoLimparFiltro }) {
  return criarEstadoVazio({
    icone: temAtivos ? "sliders" : "calendar",
    titulo: temAtivos ? "Nenhuma postagem neste filtro." : "Nenhuma postagem na Agenda.",
    descricao: temAtivos
      ? "Selecione outro status acima para visualizar as postagens."
      : "Use o Estúdio de Criação acima para gerar um post com IA, propor uma grade ou adicionar um post manual.",
    acaoLabel: temAtivos ? "Mostrar todas" : "",
    aoAcionar: temAtivos ? aoLimparFiltro : null,
    classeExtra: "agenda-empty-state",
  });
}
