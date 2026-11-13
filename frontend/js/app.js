import { apiFetch } from "/painel/js/api.js";
import { configurarTema, inicializarAuth } from "/painel/js/auth.js";
import { carregarBiblioteca, inicializarBiblioteca } from "/painel/js/biblioteca.js";
import { carregarConfigECustos, inicializarConfigECustos } from "/painel/js/config_custos.js";
import { el, limpar, notificar } from "/painel/js/dom.js";
import { carregarPlanejamentoEPosts, inicializarPlanejamento } from "/painel/js/planejamento.js";

const estado = { contaAtivaId: "" };
const obterContaAtiva = () => estado.contaAtivaId;

async function carregarDadosContaAtiva() {
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

async function carregarContas() {
  const contas = await apiFetch("/contas");
  const select = document.getElementById("select-conta");
  const aviso = document.getElementById("sem-conta-aviso");
  const main = document.getElementById("conteudo-principal");
  if (!select) return;
  limpar(select);

  if (!contas.length) {
    estado.contaAtivaId = "";
    aviso?.classList.remove("hidden");
    main?.classList.add("hidden");
    return;
  }
  aviso?.classList.add("hidden");
  main?.classList.remove("hidden");
  for (const c of contas) {
    select.appendChild(el("option", { value: c.id, text: `@${c.username}` }));
  }
  const salva = localStorage.getItem("conta_ativa_id");
  estado.contaAtivaId = contas.some((c) => c.id === salva) ? salva : contas[0].id;
  select.value = estado.contaAtivaId;
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
      const alvo = btn.getAttribute("data-sec");
      document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".painel-sec").forEach((s) => s.classList.add("hidden"));
      document.getElementById(alvo)?.classList.remove("hidden");
    });
  });

  document.getElementById("select-conta")?.addEventListener("change", (e) => {
    estado.contaAtivaId = e.target.value;
    localStorage.setItem("conta_ativa_id", estado.contaAtivaId);
    carregarDadosContaAtiva();
  });
}

configurarTema();
configurarNavegacao();
inicializarAuth(mostrarApp, mostrarLogin);
inicializarBiblioteca(obterContaAtiva);
inicializarPlanejamento(obterContaAtiva);
inicializarConfigECustos(obterContaAtiva);

apiFetch("/auth/me")
  .then((usuario) => mostrarApp(usuario))
  .catch(() => mostrarLogin());
