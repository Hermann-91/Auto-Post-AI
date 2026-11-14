import { apiFetch, apiJson } from "/painel/js/api.js";
import { el, limpar, notificar } from "/painel/js/dom.js";

export async function carregarConfigECustos(contaId) {
  if (!contaId) return;
  const [orc, cfg, fontes] = await Promise.all([
    apiFetch(`/contas/${contaId}/orcamento`),
    apiFetch(`/contas/${contaId}/ia-config`),
    apiFetch(`/contas/${contaId}/rag`),
  ]);

  const bar = document.getElementById("orcamento-bar");
  const det = document.getElementById("orcamento-detalhe");
  if (bar) bar.style.width = `${Math.min(100, orc.percentual_usado)}%`;
  if (det) {
    const modo = orc.bloqueio_orcamento ? "Bloqueio estrito" : "Fallback gratuito";
    det.textContent = `Empresa: $${orc.gasto_empresa_usd} / $${orc.limite_mensal_usd} USD (${orc.percentual_usado}%) • Conta: $${orc.gasto_conta_usd} • ${modo}`;
  }

  const form = document.getElementById("form-config-ia");
  if (form) {
    const p = cfg.persona_json || {};
    form.elements.marca.value = p.marca || "";
    form.elements.nicho.value = p.nicho || "";
    form.elements.tom_voz.value = p.tom_voz || "";
    form.elements.modelo_texto_pref.value = cfg.modelo_texto_pref || "";
    form.elements.modelo_img_pref.value = cfg.modelo_img_pref || "";
  }

  const boxRag = document.getElementById("lista-rag");
  if (!boxRag) return;
  limpar(boxRag);
  if (!fontes.length) {
    boxRag.appendChild(el("p", { className: "muted small", text: "Nenhuma fonte RAG indexada." }));
    return;
  }
  for (const f of fontes) {
    const btnDel = el("button", { type: "button", className: "btn-danger", text: "Excluir" });
    btnDel.addEventListener("click", async () => {
      try {
        await apiFetch(`/contas/${contaId}/rag/${f.id}`, { method: "DELETE" });
        notificar("Fonte RAG removida.");
        await carregarConfigECustos(contaId);
      } catch (err) { notificar(err.message, "erro"); }
    });
    boxRag.appendChild(el("div", { className: "item-card row-between" }, [
      el("div", {}, [
        el("strong", { text: `[${f.tipo}] ${f.titulo}` }),
        el("p", { className: "small muted", text: `${f.total_chunks} chunk(s)` }),
      ]),
      btnDel,
    ]));
  }
}

export function preencherFormConta(conta) {
  const modo = document.getElementById("conta-modo-edicao");
  const userEl = document.getElementById("conta-username");
  const igIdEl = document.getElementById("conta-ig-user-id");
  const tokEl = document.getElementById("conta-access-token");
  if (!modo || !userEl || !igIdEl || !tokEl) return;
  if (modo.value === "ativa" && conta) {
    userEl.value = `@${conta.username}`;
    igIdEl.value = conta.ig_user_id || "";
    tokEl.value = "";
  } else if (modo.value === "nova") {
    userEl.value = "";
    igIdEl.value = "";
    tokEl.value = "";
  }
}

export function inicializarConfigECustos(obterContaAtiva, obterContaObj, recarregarContas, ativarSecao) {
  const conectar = async () => {
    try {
      const res = await apiFetch("/meta/oauth/url");
      window.open(res.url_autorizacao, "_blank", "noopener,noreferrer");
      notificar("Fluxo OAuth aberto em nova aba.");
    } catch (err) { notificar(err.message, "erro"); }
  };
  document.getElementById("btn-conectar-meta")?.addEventListener("click", conectar);
  document.getElementById("btn-conectar-meta-vazio")?.addEventListener("click", conectar);
  document.getElementById("btn-conectar-meta-aba")?.addEventListener("click", conectar);

  const irParaConfigConta = () => {
    if (ativarSecao) ativarSecao("sec-conta-meta");
  };
  document.getElementById("btn-abrir-config-conta")?.addEventListener("click", irParaConfigConta);
  document.getElementById("btn-config-conta-vazio")?.addEventListener("click", irParaConfigConta);

  document.getElementById("conta-modo-edicao")?.addEventListener("change", () => {
    preencherFormConta(obterContaObj ? obterContaObj() : null);
  });

  document.getElementById("form-conta-ig")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const editarAtiva = fd.get("modo_edicao") === "ativa" && obterContaAtiva();
    try {
      const salva = await apiJson("/contas", "POST", {
        conta_id: editarAtiva ? obterContaAtiva() : null,
        username: String(fd.get("username") || ""),
        ig_user_id: String(fd.get("ig_user_id") || ""),
        access_token: String(fd.get("access_token") || ""),
      });
      notificar(`Conta @${salva.username} salva com criptografia Fernet!`);
      if (recarregarContas) await recarregarContas(salva.id);
    } catch (err) { notificar(err.message, "erro"); }
  });

  document.getElementById("form-config-ia")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const fd = new FormData(e.target);
    try {
      await apiJson(`/contas/${contaId}/ia-config`, "PUT", {
        persona_json: {
          marca: String(fd.get("marca") || ""),
          nicho: String(fd.get("nicho") || ""),
          tom_voz: String(fd.get("tom_voz") || ""),
        },
        templates_json: {},
        aplicar_logo_padrao: false,
        modelo_texto_pref: String(fd.get("modelo_texto_pref") || ""),
        modelo_img_pref: String(fd.get("modelo_img_pref") || ""),
      });
      notificar("Persona e modelos atualizados.");
    } catch (err) { notificar(err.message, "erro"); }
  });

  document.getElementById("form-rag")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contaId = obterContaAtiva();
    if (!contaId) return;
    const fd = new FormData(e.target);
    try {
      await apiJson(`/contas/${contaId}/rag`, "POST", {
        tipo: String(fd.get("tipo") || "TEXTO"),
        titulo: String(fd.get("titulo") || ""),
        conteudo: String(fd.get("conteudo") || ""),
      });
      notificar("Fonte RAG indexada.");
      e.target.reset();
      await carregarConfigECustos(contaId);
    } catch (err) { notificar(err.message, "erro"); }
  });
}
