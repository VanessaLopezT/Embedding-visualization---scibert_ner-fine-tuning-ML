/**
 * textPanel.js
 * Renderiza el texto analizado con las entidades encontradas.
 * - Agrupa entidades por sentencia/frase
 * - Colorea cada entidad según su tipo (model, metric, technique)
 * - Conecta con los eventos de la gráfica para resaltar en amarillo
 */

let entityMap = {};

export function renderText(data, container) {
  container.innerHTML = "";
  entityMap = {};

  const sentences = {};

  data.forEach(d => {
    if (!sentences[d.sentence_id]) {
      sentences[d.sentence_id] = {
        text: d.sentence_text,
        entities: []
      };
    }
    sentences[d.sentence_id].entities.push(d);
    entityMap[d.id] = d;
  });

  Object.values(sentences).forEach(sentence => {
    const text = sentence.text || "";
    const ranges = [];

    sentence.entities.forEach(ent => {
      const term = ent.entity || "";
      if (!term) return;

      const matches = findAllMatches(text, term);
      for (const match of matches) {
        if (!overlapsExisting(match, ranges)) {
          ranges.push({
            start: match.start,
            end: match.end,
            id: ent.id,
            label: ent.label,
            entity: term
          });
          break;
        }
      }
    });

    ranges.sort((a, b) => a.start - b.start);
    const html = buildHtmlFromRanges(text, ranges);

    const p = document.createElement("p");
    p.innerHTML = html;
    container.appendChild(p);
  });

  bindTextInteractions();
}

function bindTextInteractions() {
  // Las interacciones ahora solo vienen desde la gráfica (hover)
  // Las entidades solo se resaltan cuando se hace hover en la gráfica
}

function findAllMatches(text, term) {
  const matches = [];
  let idx = 0;
  while (idx < text.length) {
    const found = text.indexOf(term, idx);
    if (found === -1) break;
    matches.push({ start: found, end: found + term.length });
    idx = found + term.length;
  }
  return matches;
}

function overlapsExisting(range, ranges) {
  return ranges.some(r => range.start < r.end && range.end > r.start);
}

function buildHtmlFromRanges(text, ranges) {
  let result = "";
  let cursor = 0;
  for (const r of ranges) {
    if (r.start < cursor) continue;
    result += escapeHtml(text.slice(cursor, r.start));
    result += `<span class="entity ${String(r.label || "").toLowerCase()}" data-id="${r.id}">${escapeHtml(text.slice(r.start, r.end))}</span>`;
    cursor = r.end;
  }
  result += escapeHtml(text.slice(cursor));
  return result;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
