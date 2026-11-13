import { apiFetch, apiJson } from "/painel/js/api.js";
import { notificar } from "/painel/js/dom.js";

const estadoCaptcha = { habilitado: false, siteKey: "", tokens: { login: "", registro: "" } };

function carregarScriptTurnstile() {
  if (window.turnstile || document.getElementById("cf-turnstile-js")) return Promise.resolve();
  return new Promise((resolve) => {
    const s = document.createElement("script");
    s.id = "cf-turnstile-js";
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => resolve();
    document.head.appendChild(s);
  });
}

async function inicializarTurnstile() {
  const cfg = await apiFetch("/auth/config").catch(() => ({ captcha_enabled: false, turnstile_site_key: "" }));
  estadoCaptcha.habilitado = Boolean(cfg.captcha_enabled && cfg.turnstile_site_key);
  estadoCaptcha.siteKey = cfg.turnstile_site_key || "";
  if (!estadoCaptcha.habilitado) return;
  await carregarScriptTurnstile();
  if (!window.turnstile) return;
  for (const [chave, idEl] of [["login", "turnstile-login"], ["registro", "turnstile-registro"]]) {
    const alvo = document.getElementById(idEl);
    if (!alvo) continue;
    window.turnstile.render(alvo, {
      sitekey: estadoCaptcha.siteKey,
      callback: (tok) => { estadoCaptcha.tokens[chave] = tok; },
      "expired-callback": () => { estadoCaptcha.tokens[chave] = ""; },
    });
  }
}

export function configurarTema() {
  const salvo = localStorage.getItem("tema") || "dark";
  document.documentElement.setAttribute("data-theme", salvo);
  const alternar = () => {
    const atual = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", atual);
    localStorage.setItem("tema", atual);
  };
  document.getElementById("btn-tema-auth")?.addEventListener("click", alternar);
  document.getElementById("btn-tema-app")?.addEventListener("click", alternar);
}

export function inicializarAuth(aoAutenticar, aoDeslogar) {
  const tabLogin = document.getElementById("tab-login");
  const tabReg = document.getElementById("tab-registro");
  const formLogin = document.getElementById("form-login");
  const formReg = document.getElementById("form-registro");

  tabLogin?.addEventListener("click", () => {
    tabLogin.classList.add("active");
    tabReg?.classList.remove("active");
    formLogin?.classList.remove("hidden");
    formReg?.classList.add("hidden");
  });
  tabReg?.addEventListener("click", () => {
    tabReg.classList.add("active");
    tabLogin?.classList.remove("active");
    formReg?.classList.remove("hidden");
    formLogin?.classList.add("hidden");
  });

  formLogin?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(formLogin);
    try {
      const res = await apiJson("/auth/login", "POST", {
        email: String(fd.get("email") || ""),
        senha: String(fd.get("senha") || ""),
        turnstile_token: estadoCaptcha.tokens.login || "",
      });
      notificar(res.mensagem);
      aoAutenticar(res.usuario);
    } catch (err) {
      notificar(err.message, "erro");
    }
  });

  formReg?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(formReg);
    try {
      const res = await apiJson("/auth/register", "POST", {
        nome_empresa: String(fd.get("nome_empresa") || ""),
        email: String(fd.get("email") || ""),
        senha: String(fd.get("senha") || ""),
        turnstile_token: estadoCaptcha.tokens.registro || "",
      });
      notificar(res.mensagem);
      aoAutenticar(res.usuario);
    } catch (err) {
      notificar(err.message, "erro");
    }
  });

  document.getElementById("btn-logout")?.addEventListener("click", async () => {
    await apiFetch("/auth/logout", { method: "POST" }).catch(() => null);
    aoDeslogar();
  });

  inicializarTurnstile();
}
