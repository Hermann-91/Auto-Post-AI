import { el, notificar } from "/painel/js/dom.js";
import { iconeTexto } from "/painel/js/icones.js";

/**
 * Valida texto JSON garantindo que representa um objeto plano ({...}).
 */
export function parsearJsonObjeto(bruto, nomeCampo) {
  const txt = String(bruto || "").trim();
  if (!txt) return {};
  const obj = JSON.parse(txt);
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
    throw new Error(`${nomeCampo} deve ser um objeto JSON válido ({...}).`);
  }
  return obj;
}

/**
 * Conecta estilo monoespaçado, formatação e validação visual em tempo real a um textarea JSON.
 */
export function conectarEditorJson(textarea, nomeCampo) {
  if (!textarea) return { validar: () => ({}), atualizarStatus: () => true };
  textarea.classList.add("json-editor-textarea");
  textarea.setAttribute("spellcheck", "false");

  const statusBadge = el("span", { className: "badge badge-ok", text: "JSON válido" });
  const btnFormatar = el(
    "button",
    { type: "button", className: "btn-ghost btn-sm btn-inline-icone", title: `Formatar ${nomeCampo}` },
    iconeTexto("code", "Formatar", { tamanho: 13 })
  );
  const msgErro = el("span", { className: "json-erro-msg small hidden" });

  const containerLabel = textarea.closest("label");
  if (containerLabel) {
    const rotuloOriginal = containerLabel.querySelector(".json-label-txt") || containerLabel.firstChild;
    const titulo = el("span", {
      className: "json-editor-titulo",
      text: rotuloOriginal?.textContent?.trim() || nomeCampo,
    });
    if (rotuloOriginal && rotuloOriginal.nodeType === Node.TEXT_NODE) rotuloOriginal.remove();
    else if (rotuloOriginal && rotuloOriginal !== textarea) rotuloOriginal.remove();

    const header = el("div", { className: "json-editor-head" }, [
      titulo,
      el("div", { className: "row-actions" }, [statusBadge, btnFormatar]),
    ]);
    containerLabel.insertBefore(header, textarea);
    containerLabel.appendChild(msgErro);
  }

  function atualizarStatus() {
    try {
      parsearJsonObjeto(textarea.value, nomeCampo);
      textarea.classList.remove("json-invalido");
      statusBadge.className = "badge badge-ok";
      statusBadge.textContent = "JSON válido";
      msgErro.classList.add("hidden");
      msgErro.textContent = "";
      return true;
    } catch (err) {
      textarea.classList.add("json-invalido");
      statusBadge.className = "badge badge-danger";
      statusBadge.textContent = "JSON inválido";
      msgErro.classList.remove("hidden");
      msgErro.textContent = err.message;
      return false;
    }
  }

  btnFormatar.addEventListener("click", () => {
    try {
      const obj = parsearJsonObjeto(textarea.value, nomeCampo);
      textarea.value = JSON.stringify(obj, null, 2);
      atualizarStatus();
    } catch (err) {
      atualizarStatus();
      notificar(err.message, "erro");
    }
  });
  textarea.addEventListener("input", atualizarStatus);
  atualizarStatus();

  return {
    atualizarStatus,
    validar: () => {
      if (!atualizarStatus()) textarea.focus();
      return parsearJsonObjeto(textarea.value, nomeCampo);
    },
  };
}
