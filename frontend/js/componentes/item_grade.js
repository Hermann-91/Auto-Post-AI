import { el, limpar } from "/painel/js/dom.js";
import { criarIcone } from "/painel/js/icones.js";

const FORMATOS = ["IMAGE", "CAROUSEL", "REELS", "STORIES"];

function renderizarPreviaMidia(boxPrevia, item, contaId, midiaPorId) {
  limpar(boxPrevia);
  const anexoId = item.editar_midia_id || (item.midia_base_ids || [])[0];
  const anexo = anexoId ? midiaPorId.get(anexoId) : null;
  if (anexo) {
    boxPrevia.append(
      el("img", {
        src: `/biblioteca/${contaId}/midias/${anexo.id}/conteudo`,
        className: "grade-item-thumb",
        alt: "Mídia base do item",
      }),
      el("span", {
        className: "grade-item-midia-tag",
        text: item.editar_midia_id ? "Edição IA" : "Mídia base",
      })
    );
    return;
  }

  const comIA = Boolean(item.usar_ia_imagem);
  boxPrevia.appendChild(
    el("div", { className: "grade-item-placeholder" }, [
      criarIcone(comIA ? "sparkles" : "image", { tamanho: 20 }),
      el("span", { text: comIA ? "Arte por IA" : "Só texto" }),
    ])
  );
}

/**
 * Cria o mini-card visual de 2 colunas para edição de um item da grade.
 */
export function criarCardItemGrade({ item, indice, editavel, contaId, midiaPorId }) {
  const fmtAtual = FORMATOS.includes(item.formato) ? item.formato : "IMAGE";
  const badgeFmt = el("span", {
    className: `badge-fmt fmt-${fmtAtual.toLowerCase()}`,
    text: fmtAtual,
  });

  const selFormato = el("select", { className: "grade-item-select", "aria-label": "Formato" }, FORMATOS.map((f) => {
    const opt = el("option", { value: f, text: f });
    if (f === fmtAtual) opt.selected = true;
    return opt;
  }));
  const inpDia = el("input", { type: "text", className: "grade-item-dia", value: item.dia_semana || "", placeholder: "Dia", "aria-label": "Dia da semana" });
  const inpHora = el("input", { type: "text", className: "grade-item-hora", value: item.horario_sugerido || "18:00", placeholder: "18:00", "aria-label": "Horário" });
  const inpTema = el("input", { type: "text", className: "grade-item-tema", value: item.tema || "", placeholder: "Tema da publicação", "aria-label": "Tema" });

  const chkIA = el("input", { type: "checkbox" });
  chkIA.checked = Boolean(item.usar_ia_imagem);

  const txtLeg = el("textarea", { rows: "2", placeholder: "Prévia da legenda..." });
  txtLeg.value = item.legenda_previa || "";
  const txtImg = el("textarea", { rows: "2", placeholder: "Prompt da imagem (ideia visual)..." });
  txtImg.value = item.ideia_visual || "";

  for (const campo of [selFormato, inpDia, inpHora, inpTema, txtLeg, txtImg, chkIA]) {
    if (!editavel) campo.setAttribute("disabled", "disabled");
  }

  const boxPrevia = el("div", { className: "grade-item-midia" });
  renderizarPreviaMidia(boxPrevia, item, contaId, midiaPorId);

  selFormato.addEventListener("change", () => {
    item.formato = selFormato.value;
    badgeFmt.textContent = selFormato.value;
    badgeFmt.className = `badge-fmt fmt-${selFormato.value.toLowerCase()}`;
  });
  inpDia.addEventListener("input", () => { item.dia_semana = inpDia.value; });
  inpHora.addEventListener("input", () => { item.horario_sugerido = inpHora.value; });
  inpTema.addEventListener("input", () => { item.tema = inpTema.value; });
  txtLeg.addEventListener("input", () => { item.legenda_previa = txtLeg.value; });
  txtImg.addEventListener("input", () => { item.ideia_visual = txtImg.value; });
  chkIA.addEventListener("change", () => {
    item.usar_ia_imagem = chkIA.checked;
    if (!chkIA.checked && item.editar_midia_id) {
      item.midia_base_ids = [item.editar_midia_id];
      item.editar_midia_id = null;
    }
    renderizarPreviaMidia(boxPrevia, item, contaId, midiaPorId);
  });

  const topo = el("div", { className: "grade-item-topo" }, [
    el("span", { className: "grade-item-ordem", text: `#${indice + 1}` }),
    badgeFmt,
    inpTema,
    selFormato,
    inpDia,
    inpHora,
    el("label", { className: "switch small" }, [chkIA, el("span", { text: "Imagem IA" })]),
  ]);

  const campos = el("div", { className: "grade-item-campos" }, [
    el("label", { className: "small muted" }, [el("span", { text: "Legenda prévia" }), txtLeg]),
    el("label", { className: "small muted" }, [el("span", { text: "Ideia visual (prompt)" }), txtImg]),
  ]);

  return el("div", { className: "grade-item-card" }, [
    topo,
    el("div", { className: "grade-item-corpo" }, [boxPrevia, campos]),
  ]);
}
