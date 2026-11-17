const SVG_NS = "http://www.w3.org/2000/svg";

const ICON_DEFS = {
  sparkles: [
    ["path", { d: "M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9Z" }],
    ["path", { d: "M5 3v4M3 5h4M19 17v4M17 19h4" }],
  ],
  wand: [
    ["path", { d: "m15 4-1 2 2 1-2 1 1 2-2-1-1 2-1-2-2 1 1-2-2-1 2-1-1-2 2 1Z" }],
    ["path", { d: "m3 21 9-9" }],
  ],
  trash: [
    ["path", { d: "M3 6h18" }],
    ["path", { d: "M8 6V4h8v2" }],
    ["path", { d: "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" }],
    ["line", { x1: "10", y1: "11", x2: "10", y2: "17" }],
    ["line", { x1: "14", y1: "11", x2: "14", y2: "17" }],
  ],
  calendar: [
    ["rect", { x: "3", y: "4", width: "18", height: "18", rx: "2" }],
    ["line", { x1: "16", y1: "2", x2: "16", y2: "6" }],
    ["line", { x1: "8", y1: "2", x2: "8", y2: "6" }],
    ["line", { x1: "3", y1: "10", x2: "21", y2: "10" }],
  ],
  pencil: [
    ["path", { d: "M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" }],
  ],
  image: [
    ["rect", { x: "3", y: "3", width: "18", height: "18", rx: "2" }],
    ["circle", { cx: "9", cy: "9", r: "2" }],
    ["path", { d: "m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21" }],
  ],
  check: [["polyline", { points: "20 6 9 17 4 12" }]],
  refresh: [
    ["path", { d: "M21 12a9 9 0 1 1-2.64-6.36" }],
    ["polyline", { points: "21 3 21 9 15 9" }],
  ],
  moon: [["path", { d: "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" }]],
  sun: [
    ["circle", { cx: "12", cy: "12", r: "4" }],
    ["path", { d: "M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" }],
  ],
  logout: [
    ["path", { d: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" }],
    ["polyline", { points: "16 17 21 12 16 7" }],
    ["line", { x1: "21", y1: "12", x2: "9", y2: "12" }],
  ],
  upload: [
    ["path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" }],
    ["polyline", { points: "17 8 12 3 7 8" }],
    ["line", { x1: "12", y1: "3", x2: "12", y2: "15" }],
  ],
  sliders: [
    ["line", { x1: "4", y1: "21", x2: "4", y2: "14" }],
    ["line", { x1: "4", y1: "10", x2: "4", y2: "3" }],
    ["line", { x1: "12", y1: "21", x2: "12", y2: "12" }],
    ["line", { x1: "12", y1: "8", x2: "12", y2: "3" }],
    ["line", { x1: "20", y1: "21", x2: "20", y2: "16" }],
    ["line", { x1: "20", y1: "12", x2: "20", y2: "3" }],
    ["line", { x1: "1", y1: "14", x2: "7", y2: "14" }],
    ["line", { x1: "9", y1: "8", x2: "15", y2: "8" }],
    ["line", { x1: "17", y1: "16", x2: "23", y2: "16" }],
  ],
  chevronDown: [["polyline", { points: "6 9 12 15 18 9" }]],
  chevronRight: [["polyline", { points: "9 18 15 12 9 6" }]],
  plus: [
    ["line", { x1: "12", y1: "5", x2: "12", y2: "19" }],
    ["line", { x1: "5", y1: "12", x2: "19", y2: "12" }],
  ],
  layers: [
    ["polygon", { points: "12 2 2 7 12 12 22 7 12 2" }],
    ["polyline", { points: "2 17 12 22 22 17" }],
    ["polyline", { points: "2 12 12 17 22 12" }],
  ],
  send: [
    ["line", { x1: "22", y1: "2", x2: "11", y2: "13" }],
    ["polygon", { points: "22 2 15 22 11 13 2 9 22 2" }],
  ],
  alertCircle: [
    ["circle", { cx: "12", cy: "12", r: "10" }],
    ["line", { x1: "12", y1: "8", x2: "12", y2: "12" }],
    ["line", { x1: "12", y1: "16", x2: "12.01", y2: "16" }],
  ],
  heart: [
    ["path", { d: "M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" }],
  ],
  bookOpen: [
    ["path", { d: "M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" }],
    ["path", { d: "M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" }],
  ],
  globe: [
    ["circle", { cx: "12", cy: "12", r: "10" }],
    ["line", { x1: "2", y1: "12", x2: "22", y2: "12" }],
    ["path", { d: "M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" }],
  ],
  fileText: [
    ["path", { d: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" }],
    ["polyline", { points: "14 2 14 8 20 8" }],
    ["line", { x1: "16", y1: "13", x2: "8", y2: "13" }],
    ["line", { x1: "16", y1: "17", x2: "8", y2: "17" }],
  ],
  dollarSign: [
    ["line", { x1: "12", y1: "1", x2: "12", y2: "23" }],
    ["path", { d: "M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" }],
  ],
  shield: [["path", { d: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" }]],
  database: [
    ["ellipse", { cx: "12", cy: "5", rx: "9", ry: "3" }],
    ["path", { d: "M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" }],
    ["path", { d: "M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" }],
  ],
  code: [
    ["polyline", { points: "16 18 22 12 16 6" }],
    ["polyline", { points: "8 6 2 12 8 18" }],
  ],
  externalLink: [
    ["path", { d: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" }],
    ["polyline", { points: "15 3 21 3 21 9" }],
    ["line", { x1: "10", y1: "14", x2: "21", y2: "3" }],
  ],
};

export function criarIcone(nome, { tamanho = 16, classe = "", titulo = "", preenchido = false } = {}) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("width", String(tamanho));
  svg.setAttribute("height", String(tamanho));
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", preenchido ? "currentColor" : "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", classe ? `icone-svg ${classe}` : "icone-svg");
  if (titulo) {
    const titleEl = document.createElementNS(SVG_NS, "title");
    titleEl.textContent = titulo;
    svg.appendChild(titleEl);
  }
  for (const [tag, attrs] of ICON_DEFS[nome] || ICON_DEFS.sparkles) {
    const shape = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) shape.setAttribute(k, v);
    svg.appendChild(shape);
  }
  return svg;
}

export function iconeTexto(nome, texto, opcoes = {}) {
  const span = document.createElement("span");
  span.textContent = texto;
  return [criarIcone(nome, opcoes), span];
}
