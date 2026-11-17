import { apiFetch, apiJson } from "/painel/js/api.js";
import { notificar } from "/painel/js/dom.js";

function parsearJsonObjeto(bruto, nomeCampo) {
  const txt = String(bruto || "").trim();
  if (!txt) return {};
  const obj = JSON.parse(txt);
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
    throw new Error(`${nomeCampo} deve ser um objeto JSON válido ({...}).`);
  }
  return obj;
}

export async function carregarConfigECustos(contaId) {
  if (!contaId) return;
  const [orc, cfg] = await Promise.all([
    apiFetch(`/contas/${contaId}/orcamento`),
    apiFetch(`/contas/${contaId}/ia-config`),
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
    form.elements.regiao.value = p.regiao || "";
    form.elements.tom_voz.value = p.tom_voz || "";
    form.elements.publico_alvo.value = p.publico_alvo || "";
    form.elements.cta_padrao.value = p.cta_padrao || "";
    form.elements.restricoes.value = p.restricoes || "";
    form.elements.modelo_texto_pref.value = cfg.modelo_texto_pref || "";
    form.elements.modelo_img_pref.value = cfg.modelo_img_pref || "";
    form.elements.aplicar_logo_padrao.checked = Boolean(cfg.aplicar_logo_padrao);
    form.elements.templates_json.value = JSON.stringify(cfg.templates_json || {}, null, 2);
    form.elements.brand_bible_json.value = JSON.stringify(cfg.brand_bible_json || {}, null, 2);
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
  document.getElementById("btn-conectar-meta-vazio")?.addEventListener("click", conectar);
  document.getElementById("btn-conectar-meta-aba")?.addEventListener("click", conectar);

  const irParaConfigConta = () => {
    if (ativarSecao) ativarSecao("sec-conta-meta");
  };
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
      const templates = parsearJsonObjeto(fd.get("templates_json"), "Templates JSON");
      const brandBible = parsearJsonObjeto(fd.get("brand_bible_json"), "Brand Bible JSON");
      const salva = await apiJson(`/contas/${contaId}/ia-config`, "PUT", {
        persona_json: {
          marca: String(fd.get("marca") || ""),
          nicho: String(fd.get("nicho") || ""),
          regiao: String(fd.get("regiao") || ""),
          tom_voz: String(fd.get("tom_voz") || ""),
          publico_alvo: String(fd.get("publico_alvo") || ""),
          cta_padrao: String(fd.get("cta_padrao") || ""),
          restricoes: String(fd.get("restricoes") || ""),
        },
        templates_json: templates,
        brand_bible_json: brandBible,
        aplicar_logo_padrao: Boolean(fd.get("aplicar_logo_padrao")),
        modelo_texto_pref: String(fd.get("modelo_texto_pref") || ""),
        modelo_img_pref: String(fd.get("modelo_img_pref") || ""),
      });
      e.target.elements.brand_bible_json.value = JSON.stringify(salva.brand_bible_json || {}, null, 2);
      notificar("Configuração, Templates e Brand Bible salvos!");
    } catch (err) { notificar(err.message, "erro"); }
  });

  const compilarBible = async (usarIa, btn) => {
    const contaId = obterContaAtiva();
    if (!contaId) return;
    btn.setAttribute("disabled", "disabled");
    try {
      const cfg = await apiJson(`/contas/${contaId}/brand-bible/compilar`, "POST", { usar_ia: usarIa });
      const form = document.getElementById("form-config-ia");
      if (form) form.elements.brand_bible_json.value = JSON.stringify(cfg.brand_bible_json || {}, null, 2);
      notificar(usarIa ? "Brand Bible enriquecida com IA!" : "Brand Bible compilada ($0)!");
    } catch (err) { notificar(err.message, "erro"); }
    finally { btn.removeAttribute("disabled"); }
  };
  document.getElementById("btn-compilar-bible-zero")?.addEventListener("click", (e) => compilarBible(false, e.currentTarget));
  document.getElementById("btn-compilar-bible-ia")?.addEventListener("click", (e) => compilarBible(true, e.currentTarget));
}
