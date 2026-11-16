import { apiFetch } from "/painel/js/api.js";
import { configurarTema, inicializarAuth } from "/painel/js/auth.js";
import { carregarBiblioteca, inicializarBiblioteca } from "/painel/js/biblioteca.js";
import { carregarConfigECustos, inicializarConfigECustos, preencherFormConta } from "/painel/js/config_custos.js";
import { el, limpar, notificar } from "/painel/js/dom.js";
import { carregarPlanejamentoEPosts, inicializarPlanejamento } from "/painel/js/planejamento.js";

const estado = { contaAtivaId: "", contas: [] };
const obterContaAtiva = () => estado.contaAtivaId;
const obterContaAtivaObj = () => estado.contas.find((c) => c.id === estado.contaAtivaId) || null;

export function ativarSecao(alvo) {
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.getAttribute("data-sec") === alvo));
  document.querySelectorAll(".painel-sec").forEach((s) => s.classList.toggle("hidden", s.id !== alvo));
}

function renderizarAbasContas() {
  const barra = document.getElementById("abas-contas-dinamicas");
  if (!barra) return;
  limpar(barra);
  if (!estado.contas.length) return barra.classList.add("hidden");
  barra.classList.remove("hidden");
  for (const c of estado.contas) {
    const btn = el("button", {
      type: "button",
      className: `conta-tab-btn ${c.id === estado.contaAtivaId ? "active" : ""}`,
      text: `@${c.username}`,
    });
    btn.addEventListener("click", () => selecionarContaAtiva(c.id));
    barra.appendChild(btn);
  }
  const btnAdd = el("button", { type: "button", className: "btn-ghost small", text: "+ Conta" });
  btnAdd.addEventListener("click", () => ativarSecao("sec-conta-meta"));
  barra.appendChild(btnAdd);
}

function selecionarContaAtiva(contaId) {
  estado.contaAtivaId = contaId;
  localStorage.setItem("conta_ativa_id", contaId);
  const select = document.getElementById("select-conta");
  if (select) select.value = contaId;
  renderizarAbasContas();
  return carregarDadosContaAtiva();
}

async function carregarDadosContaAtiva() {
  preencherFormConta(obterContaAtivaObj());
  if (!estado.contaAtivaId) return;
  try {
    await Promise.all([
      carregarBiblioteca(estado.contaAtivaId),
      carregarPlanejamentoEPosts(estado.contaAtivaId),
      carregarConfigECustos(estado.contaAtivaId),
    ]);
  } catch (err) {
    notificar(err.message, "erro");
  }
}

async function carregarContas(contaPreferidaId = "") {
  const contas = await apiFetch("/contas");
  estado.contas = contas;
  const select = document.getElementById("select-conta");
  const aviso = document.getElementById("sem-conta-aviso");
  const main = document.getElementById("conteudo-principal");
  if (!select) return;
  limpar(select);
  main?.classList.remove("hidden");

  if (!contas.length) {
    estado.contaAtivaId = "";
    select.appendChild(el("option", { value: "", text: "Sem conta" }));
    aviso?.classList.remove("hidden");
    renderizarAbasContas();
    ativarSecao("sec-conta-meta");
    preencherFormConta(null);
    return;
  }
  aviso?.classList.add("hidden");
  for (const c of contas) {
    select.appendChild(el("option", { value: c.id, text: `@${c.username}` }));
  }
  const salva = contaPreferidaId || localStorage.getItem("conta_ativa_id");
  estado.contaAtivaId = contas.some((c) => c.id === salva) ? salva : contas[0].id;
  select.value = estado.contaAtivaId;
  localStorage.setItem("conta_ativa_id", estado.contaAtivaId);
  renderizarAbasContas();
  await carregarDadosContaAtiva();
}

function mostrarApp(usuario) {
  document.getElementById("auth-view")?.classList.add("hidden");
  document.getElementById("app-view")?.classList.remove("hidden");
  const emailEl = document.getElementById("usuario-email");
  if (emailEl) emailEl.textContent = usuario.email;
  carregarContas().catch((err) => notificar(err.message, "erro"));
}

function mostrarLogin() {
  estado.contaAtivaId = "";
  document.getElementById("app-view")?.classList.add("hidden");
  document.getElementById("auth-view")?.classList.remove("hidden");
}

function configurarNavegacao() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      ativarSecao(btn.getAttribute("data-sec"));
    });
  });

  document.getElementById("select-conta")?.addEventListener("change", (e) => selecionarContaAtiva(e.target.value));
}

configurarTema();
configurarNavegacao();
inicializarAuth(mostrarApp, mostrarLogin);
inicializarBiblioteca(obterContaAtiva);
inicializarPlanejamento(obterContaAtiva);
inicializarConfigECustos(
  obterContaAtiva,
  obterContaAtivaObj,
  (novoId) => carregarContas(novoId),
  ativarSecao
);

apiFetch("/auth/me")
  .then((usuario) => mostrarApp(usuario))
  .catch(() => mostrarLogin());
