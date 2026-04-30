/**
 * textPanel.js
 * Renderiza el texto analizado con las entidades encontradas.
 * - Agrupa entidades por sentencia/frase
 * - Colorea cada entidad según su tipo (tech o CMT)
 * - Conecta con los eventos de la gráfica para resaltar en amarillo
 */

import { getColorForLabel } from "./categoryColors.js";

let entityMap = {};

export function renderText(data, container, externalTitle = null, options = {}) {
  const mode = options.mode === "all" ? "all" : "entities";
  const cleanedText = typeof options.cleanedText === "string" ? options.cleanedText : "";
  container.innerHTML = "";
  entityMap = {};
  let titleRendered = false;

  const sentences = new Map();

  data.forEach(d => {
    if (!sentences.has(d.sentence_id)) {
      sentences.set(d.sentence_id, {
        text: d.sentence_text,
        entities: []
      });
    }
    sentences.get(d.sentence_id).entities.push(d);
    entityMap[d.id] = d;
  });

  let titleSentence = null;
  const sentenceList = Array.from(sentences.values());
  sentenceList.forEach(sentence => {
    const text = sentence.text || "";
    if (!titleSentence && /^TITLE:\s*/i.test(text.trim())) {
      titleSentence = sentence;
    }
  });

  const cleanExternalTitle = sanitizeTitle(String(externalTitle || "").trim());
  const fallbackTitle = titleSentence
    ? sanitizeTitle(String(titleSentence.text || "").replace(/^TITLE:\s*/i, "").trim())
    : "";
  const titleText = cleanExternalTitle || fallbackTitle;

  if (titleText) {
    const titleRanges = [];
    const sourceEntities = titleSentence ? (titleSentence.entities || []) : [];
    sourceEntities.forEach(ent => {
      const term = ent.entity || "";
      if (!term) return;
      const matches = findAllMatches(titleText, term);
      for (const match of matches) {
        if (!overlapsExisting(match, titleRanges)) {
          titleRanges.push({
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
    titleRanges.sort((a, b) => a.start - b.start);

    const h = document.createElement("h3");
    h.className = "article-title";
    if (titleRanges.length > 0) {
      h.innerHTML = buildHtmlFromRanges(titleText, titleRanges);
    } else {
      h.textContent = titleText;
    }
    container.appendChild(h);

    const spacer = document.createElement("div");
    spacer.className = "title-spacer";
    container.appendChild(spacer);
    titleRendered = true;
  }

  if (mode === "all" && cleanedText) {
    const paragraphs = extractBodyParagraphsFromCleanedText(cleanedText);
    paragraphs.forEach(paragraph => {
      const p = document.createElement("p");
      p.textContent = paragraph;
      container.appendChild(p);
    });
    bindTextInteractions();
    return;
  }

  if (mode === "entities" && cleanedText) {
    if (hasExactEntityOffsets(sentenceList)) {
      renderExactSentenceBlocks(sentenceList, container, { skipTitle: titleRendered });
      bindTextInteractions();
      return;
    }

    const paragraphs = buildEntityParagraphs(cleanedText, sentenceList);
    paragraphs.forEach(paragraph => {
      const ranges = [];
      paragraph.entities.forEach(ent => {
        const term = ent.entity || "";
        if (!term) return;

        const matches = findAllMatches(paragraph.text, term);
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
      const p = document.createElement("p");
      p.innerHTML = buildHtmlFromRanges(paragraph.text, ranges);
      container.appendChild(p);
    });
    bindTextInteractions();
    return;
  }

  sentenceList.forEach(sentence => {
    const text = sentence.text || "";
    const isTitle = /^TITLE:\s*/i.test(text.trim());
    if (isTitle) {
      if (titleRendered) return;
      const h = document.createElement("h3");
      h.className = "article-title";
      h.textContent = text.replace(/^TITLE:\s*/i, "").trim();
      container.appendChild(h);
      const spacer = document.createElement("div");
      spacer.className = "title-spacer";
      container.appendChild(spacer);
      titleRendered = true;
      return;
    }

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

function hasExactEntityOffsets(sentenceList) {
  return Array.isArray(sentenceList) && sentenceList.some(sentence =>
    Array.isArray(sentence?.entities) && sentence.entities.some(ent =>
      Number.isInteger(ent?.start) && Number.isInteger(ent?.end)
    )
  );
}

function renderExactSentenceBlocks(sentenceList, container, options = {}) {
  const skipTitle = Boolean(options.skipTitle);

  sentenceList.forEach(sentence => {
    const text = String(sentence?.text || "");
    const isTitle = /^TITLE:\s*/i.test(text.trim());
    if (isTitle && skipTitle) return;

    const ranges = buildExactRanges(text, sentence.entities || []);
    if (!ranges.length) return;

    const el = document.createElement(isTitle ? "h3" : "p");
    if (isTitle) {
      el.className = "article-title";
    }
    el.innerHTML = buildHtmlFromRanges(text, ranges);
    container.appendChild(el);

    if (isTitle) {
      const spacer = document.createElement("div");
      spacer.className = "title-spacer";
      container.appendChild(spacer);
    }
  });
}

function buildExactRanges(text, entities) {
  const ranges = [];
  const sourceText = String(text || "");

  (Array.isArray(entities) ? entities : []).forEach(ent => {
    const start = Number(ent?.start);
    const end = Number(ent?.end);
    if (!Number.isInteger(start) || !Number.isInteger(end)) return;
    if (start < 0 || end <= start || end > sourceText.length) return;

    ranges.push({
      start,
      end,
      id: ent.id,
      sentenceId: ent.sentence_id,
      label: ent.label,
      entity: ent.entity || sourceText.slice(start, end)
    });
  });

  ranges.sort((a, b) => a.start - b.start || a.end - b.end);
  return ranges.filter((range, index) => {
    if (index === 0) return true;
    const prev = ranges[index - 1];
    return range.start >= prev.end;
  });
}

function bindTextInteractions() {
  // Las interacciones ahora solo vienen desde la gráfica (hover)
  // Las entidades solo se resaltan cuando se hace hover en la gráfica
}

function findAllMatches(text, term) {
  const matches = [];
  const haystack = String(text || "");
  const needle = String(term || "");
  const haystackLower = haystack.toLowerCase();
  const needleLower = needle.toLowerCase();
  if (!needleLower) return matches;
  let idx = 0;
  while (idx < haystackLower.length) {
    const found = haystackLower.indexOf(needleLower, idx);
    if (found === -1) break;
    matches.push({ start: found, end: found + needle.length });
    idx = found + needle.length;
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
    const _color = getColorForLabel(r.label);
    const sentenceAttr = Number.isInteger(r.sentenceId) ? ` data-sentence-id="${r.sentenceId}"` : "";
    const startAttr = Number.isInteger(r.start) ? ` data-start="${r.start}"` : "";
    const endAttr = Number.isInteger(r.end) ? ` data-end="${r.end}"` : "";
    result += `<span class="entity" data-id="${r.id}"${sentenceAttr}${startAttr}${endAttr} data-entity-key="${escapeHtml(normalizeEntityKey(r.entity || text.slice(r.start, r.end)))}" data-label="${escapeHtml(String(r.label || ""))}" style="color:${_color}; border-bottom: 2px solid ${_color};">${escapeHtml(text.slice(r.start, r.end))}</span>`;
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

function sanitizeTitle(title) {
  let t = String(title || "").trim();
  if (!t) return "";
  // Si viene pegado con abstract/keywords, cortar ese ruido.
  t = t.replace(/\bA\W*B\W*S\W*T\W*R\W*A\W*C\W*T\b[\s\S]*$/i, "").trim();
  t = t.replace(/\bAbstract\b[\s\S]*$/i, "").trim();
  t = t.replace(/\s{2,}/g, " ").trim();
  return t;
}

export function getEntityParagraphs(data, cleanedText = "") {
  const sentences = new Map();
  (Array.isArray(data) ? data : []).forEach(d => {
    if (!sentences.has(d.sentence_id)) {
      sentences.set(d.sentence_id, {
        text: d.sentence_text,
        entities: []
      });
    }
    sentences.get(d.sentence_id).entities.push(d);
  });
  return buildEntityParagraphs(cleanedText, Array.from(sentences.values()));
}

function buildEntityParagraphs(cleanedText, sentenceList) {
  const paragraphs = extractBodyParagraphsFromCleanedText(cleanedText);
  if (!paragraphs.length) return [];

  const normalizedParagraphs = paragraphs.map((text, index) => ({
    index,
    text,
    normalized: normalizeForParagraphMatch(text),
    entities: []
  }));

  const entityOccurrences = [];
  sentenceList.forEach(sentence => {
    const rawText = String(sentence?.text || "").trim();
    if (!rawText || /^TITLE:\s*/i.test(rawText)) return;
    (sentence.entities || []).forEach(ent => {
      entityOccurrences.push(ent);
    });
  });

  entityOccurrences.forEach(ent => {
    const rawEntity = String(ent?.entity || "").trim();
    if (!rawEntity) return;

    const normalizedEntity = normalizeForParagraphMatch(rawEntity);
    if (!normalizedEntity) return;

    normalizedParagraphs.forEach(paragraph => {
      if (!paragraph.normalized.includes(normalizedEntity)) return;
      if (!paragraph.entities.some(existing => existing.id === ent.id)) {
        paragraph.entities.push(ent);
      }
    });
  });

  return normalizedParagraphs.filter(paragraph => paragraph.entities.length > 0);
}

function normalizeForParagraphMatch(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[“”"']/g, "")
    .replace(/\s*([.,:;!?()[\]{}])\s*/g, "$1")
    .replace(/\s*-\s*/g, "-")
    .replace(/\s*\/\s*/g, "/")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeEntityKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[“”"']/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function extractBodyParagraphsFromCleanedText(cleanedText) {
  const text = String(cleanedText || "").trim();
  if (!text) return [];

  return text
    .split(/\r?\n\s*\r?\n/)
    .map(p => p.trim())
    .filter(Boolean)
    .flatMap(p => {
      if (!/^TITLE:\s*/i.test(p)) return [p];
      const withoutTitle = p.replace(/^TITLE:\s*[^\r\n]*\s*/i, "").trim();
      return withoutTitle ? [withoutTitle] : [];
    });
}
