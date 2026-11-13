export function el(tag, attrs = {}, filhos = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "className") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (v !== undefined && v !== null) node.setAttribute(k, String(v));
  }
  for (const filho of filhos) {
    if (typeof filho === "string") node.appendChild(document.createTextNode(filho));
    else if (filho) node.appendChild(filho);
  }
  return node;
}

export function limpar(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function notificar(mensagem, tipo = "ok") {
  const box = document.getElementById("toast-container");
  if (!box) return;
  const item = el("div", { className: `toast ${tipo}`, text: mensagem });
  box.appendChild(item);
  setTimeout(() => item.remove(), 4200);
}

export function formatarBytes(bytes) {
  if (!bytes) return "0 B";
  const unidades = ["B", "KB", "MB", "GB"];
  const idx = Math.min(unidades.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** idx).toFixed(1)} ${unidades[idx]}`;
}
