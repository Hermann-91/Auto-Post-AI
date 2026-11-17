function lerCookie(nome) {
  const partes = document.cookie ? document.cookie.split("; ") : [];
  for (const parte of partes) {
    const idx = parte.indexOf("=");
    if (idx > 0 && parte.slice(0, idx) === nome) {
      return decodeURIComponent(parte.slice(idx + 1));
    }
  }
  return "";
}

async function extrairErro(resp) {
  try {
    const corpo = await resp.json();
    return corpo.detail || `Erro HTTP ${resp.status}`;
  } catch {
    return `Erro HTTP ${resp.status}`;
  }
}

const ROTAS_SEM_REFRESH = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
  "/auth/logout",
  "/auth/config",
]);

export async function apiFetch(caminho, opcoes = {}, tentarRefresh = true) {
  const metodo = (opcoes.method || "GET").toUpperCase();
  const headers = new Headers(opcoes.headers || {});
  if (["POST", "PUT", "PATCH", "DELETE"].includes(metodo)) {
    const csrf = lerCookie("csrf_token");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const resp = await fetch(caminho, {
    ...opcoes,
    method: metodo,
    headers,
    credentials: "include",
  });

  if (resp.status === 401 && tentarRefresh && !ROTAS_SEM_REFRESH.has(caminho)) {
    const ref = await apiFetch("/auth/refresh", { method: "POST" }, false).catch(() => null);
    if (ref) return apiFetch(caminho, opcoes, false);
  }

  if (!resp.ok) throw new Error(await extrairErro(resp));
  if (resp.status === 204) return null;
  const ct = resp.headers.get("content-type") || "";
  return ct.includes("application/json") ? resp.json() : resp;
}

export function apiJson(caminho, metodo, body) {
  return apiFetch(caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function esperar(ms, signal) {
  return new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    if (!signal) return;
    signal.addEventListener("abort", () => {
      clearTimeout(id);
      reject(new DOMException("Polling cancelado.", "AbortError"));
    }, { once: true });
  });
}

export async function acompanharJobIA(jobId, { aoProgredir = null, signal = null } = {}) {
  let esperaMs = 350;
  while (true) {
    if (signal?.aborted) throw new DOMException("Polling cancelado.", "AbortError");
    const job = await apiFetch(`/ia/jobs/${jobId}`, { signal });
    if (aoProgredir) aoProgredir(job);
    if (job.status === "CONCLUIDO") return job;
    if (job.status === "FALHA") throw new Error(job.erro_detalhe || "Falha ao processar job de IA.");
    await esperar(esperaMs, signal);
    esperaMs = Math.min(1200, esperaMs + 150);
  }
}

export async function executarJobIA({
  contaId, tipoJob, payload, chaveIdempotencia = "", aoProgredir = null, signal = null,
}) {
  const inicial = await apiJson("/ia/jobs", "POST", {
    conta_ig_id: contaId, tipo_job: tipoJob, chave_idempotencia: chaveIdempotencia, ...payload,
  });
  if (aoProgredir) aoProgredir(inicial);
  if (inicial.status === "CONCLUIDO") return inicial;
  if (inicial.status === "FALHA") throw new Error(inicial.erro_detalhe || "Falha ao iniciar job.");
  return acompanharJobIA(inicial.id, { aoProgredir, signal });
}
