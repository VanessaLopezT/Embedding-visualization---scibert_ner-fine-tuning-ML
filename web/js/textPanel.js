/**
 * textPanel.js
 * Renderiza el texto analizado con las entidades encontradas.
 * - Agrupa entidades por sentencia/frase
 * - Colorea cada entidad según su tipo (tech o CMT)
 * - Conecta con los eventos de la gráfica para resaltar en amarillo
 */

import { getColorForLabel } from "./categoryColors.js";

let entityMap = {};

/**
 * Agrupa ocurrencias por la frase exacta que usa cada modelo (sentence_text).
 * Si solo se agrupa por sentence_id, la primera frase "gana" y los start/end de
 * otro modelo (p. ej. PatVet con otra capitalización) dejan de coincidir: no se
 * subraya al hacer hover en el gráfico.
 */
function clusterSentenceRecords(data) {
  const sentences = new Map();
  (Array.isArray(data) ? data : []).forEach(d => {
    const sid = d.sentence_id;
    const st = String(d.sentence_text ?? "");
    const key = `${sid}\x1e${st}`;
    if (!sentences.has(key)) {
      sentences.set(key, {
        sentence_id: sid,
        text: st,
        entities: [],
      });
    }
    sentences.get(key).entities.push(d);
  });
  return Array.from(sentences.entries())
    .sort(([ka], [kb]) => compareSentenceClusterKeys(ka, kb))
    .map(([, v]) => v);
}

function compareSentenceClusterKeys(ka, kb) {
  const [sa, ta] = String(ka).split("\x1e");
  const [sb, tb] = String(kb).split("\x1e");
  const na = Number(sa) - Number(sb);
  if (Number.isFinite(na) && na !== 0) return na;
  return String(ta).localeCompare(String(tb));
}

/** Misma convención que el backend (`TITLE:` al inicio de línea). */
function extractTitleLineFromCleaned(cleanedText) {
  const lines = String(cleanedText || "").split(/\r?\n/);
  for (let i = 0; i < Math.min(lines.length, 30); i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const m = line.match(/^TITLE:\s*(.+)$/i);
    if (m) return m[1].trim();
  }
  return "";
}

/**
 * Desplaza un panel con overflow para centrar un elemento hijo.
 * `element.offsetTop` no sirve aquí: es relativo a `offsetParent` (p. ej. un párrafo), no al #text-panel.
 */
export function scrollPanelElementIntoView(panel, entityEl, options = {}) {
  if (!panel || !entityEl || typeof panel.getBoundingClientRect !== "function") return;
  const behavior = options.behavior === "auto" ? "auto" : "smooth";
  const elRect = entityEl.getBoundingClientRect();
  const panelRect = panel.getBoundingClientRect();
  const relativeTop = elRect.top - panelRect.top + panel.scrollTop;
  const targetTop = relativeTop - panel.clientHeight / 2 + elRect.height / 2;
  const maxScroll = Math.max(0, panel.scrollHeight - panel.clientHeight);
  const top = Math.max(0, Math.min(targetTop, maxScroll));
  panel.scrollTo({ top, behavior });
}

export function renderText(data, container, externalTitle = null, options = {}) {
  const mode = options.mode === "all" ? "all" : "entities";
  const cleanedText = typeof options.cleanedText === "string" ? options.cleanedText : "";
  container.innerHTML = "";
  entityMap = {};
  let titleRendered = false;
  let titleSentence = null;

  const sentenceList = clusterSentenceRecords(data);

  sentenceList.forEach(sentence => {
    (sentence.entities || []).forEach(ent => {
      entityMap[ent.id] = ent;
    });
    const text = sentence.text || "";
    if (!titleSentence && /^TITLE:\s*/i.test(text.trim())) {
      titleSentence = sentence;
    }
  });

  const cleanExternalTitle = sanitizeTitle(String(externalTitle || "").trim());
  const titleFromCleanedRaw = extractTitleLineFromCleaned(cleanedText);
  const titleFromCleaned = titleFromCleanedRaw ? sanitizeTitle(titleFromCleanedRaw) : "";
  const fallbackTitleFromSentence = titleSentence
    ? sanitizeTitle(String(titleSentence.text || "").replace(/^TITLE:\s*/i, "").trim())
    : "";
  // Mismo aspecto en tech / PatVet / ambos: priorizar título alineado con `cleaned_text.txt`.
  const titleText = cleanExternalTitle || titleFromCleaned || fallbackTitleFromSentence;

  if (titleText) {
    const titleOccPainted = new Set();
    const titleIdPainted = new Set();
    const titleRanges = [];
    const sourceEntities = sortEntitiesByDocPosition(titleSentence ? (titleSentence.entities || []) : []);
    sourceEntities.forEach(ent => {
      const term = ent.entity || "";
      if (!term) return;
      const occurrenceKey = backendOccurrenceKey(ent);
      if (occurrenceKey && titleOccPainted.has(occurrenceKey)) return;
      const idStr = ent?.id !== undefined && ent?.id !== null ? String(ent.id) : "";
      if (idStr && titleIdPainted.has(idStr)) return;

      const matches = entityMatchCandidatesInParagraph(titleText, term);
      const sid = Number(ent.sentence_id);
      for (const match of matches) {
        if (!overlapsExisting(match, titleRanges)) {
          titleRanges.push({
            start: match.start,
            end: match.end,
            id: ent.id,
            label: ent.label,
            entity: term,
            sentenceId: Number.isFinite(sid) ? Math.round(sid) : undefined,
            occurrenceKey: occurrenceKey || undefined,
          });
          if (occurrenceKey) titleOccPainted.add(occurrenceKey);
          if (idStr) titleIdPainted.add(idStr);
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
    // Mismo cuerpo para Tech, PatVet y vista combinada: `cleanedText` es la fuente única.
    // No usar `sentence_text` por modelo con offsets (PatVet y Tech pueden diferir del limpio).
    const bodyOccPainted = new Set();
    const bodyIdPainted = new Set();
    const paragraphs = buildEntityParagraphs(cleanedText, sentenceList);
    paragraphs.forEach(paragraph => {
      const ranges = [];
      sortEntitiesByDocPosition(paragraph.entities).forEach(ent => {
        const term = ent.entity || "";
        if (!term) return;

        const occurrenceKey = backendOccurrenceKey(ent);
        if (occurrenceKey && bodyOccPainted.has(occurrenceKey)) return;
        const idStr = ent?.id !== undefined && ent?.id !== null ? String(ent.id) : "";
        if (idStr && bodyIdPainted.has(idStr)) return;

        const matchList = entityMatchCandidatesInParagraph(paragraph.text, term);
        const sid = Number(ent.sentence_id);
        for (const match of matchList) {
          if (!overlapsExisting(match, ranges)) {
            ranges.push({
              start: match.start,
              end: match.end,
              id: ent.id,
              label: ent.label,
              entity: term,
              sentenceId: Number.isFinite(sid) ? Math.round(sid) : undefined,
              occurrenceKey: occurrenceKey || undefined,
            });
            if (occurrenceKey) bodyOccPainted.add(occurrenceKey);
            if (idStr) bodyIdPainted.add(idStr);
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

    sortEntitiesByDocPosition(sentence.entities).forEach(ent => {
      const term = ent.entity || "";
      if (!term) return;

      const matches = entityMatchCandidatesInParagraph(text, term);
      const sid = Number(ent.sentence_id);
      const occurrenceKey = backendOccurrenceKey(ent);
      for (const match of matches) {
        if (!overlapsExisting(match, ranges)) {
          ranges.push({
            start: match.start,
            end: match.end,
            id: ent.id,
            label: ent.label,
            entity: term,
            sentenceId: Number.isFinite(sid) ? Math.round(sid) : undefined,
            occurrenceKey: occurrenceKey || undefined,
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

/** Variantes del término para enlazar texto limpio ↔ etiqueta NER (espacios, guiones, etc.). */
function entityMatchCandidatesInParagraph(paragraphText, term) {
  const raw = String(term || "").trim();
  if (!raw) return [];
  let m = findAllMatches(paragraphText, raw);
  if (m.length) return m;
  const collapsed = raw.replace(/\s+/g, " ");
  if (collapsed !== raw) {
    m = findAllMatches(paragraphText, collapsed);
    if (m.length) return m;
  }
  const detok = raw.replace(/##/g, "").replace(/\s+/g, " ").trim();
  if (detok && detok !== raw) {
    m = findAllMatches(paragraphText, detok);
    if (m.length) return m;
  }
  const norm = normalizeForParagraphMatch(raw);
  if (norm && norm.length >= 2) {
    m = findAllMatches(paragraphText, norm);
    if (m.length) return m;
  }
  return [];
}

function overlapsExisting(range, ranges) {
  return ranges.some(r => range.start < r.end && range.end > r.start);
}

/**
 * Clave estable alineada con filas t-SNE/JSON (sentence_id + start/end en frase del modelo).
 * Distinto de data-start/data-end en el DOM, que son offsets dentro del párrafo renderizado.
 * No usar Number(null) (sería 0). JSON puede mandar floats enteros (12.0).
 */
export function backendOccurrenceKey(ent) {
  if (ent == null || typeof ent !== "object") return "";
  const rawSid = ent.sentence_id;
  const rawSt = ent.start;
  const rawEn = ent.end;
  if (rawSid == null || rawSt == null || rawEn == null) return "";
  const sid = Number(rawSid);
  const st = Number(rawSt);
  const en = Number(rawEn);
  if (!Number.isFinite(sid) || !Number.isFinite(st) || !Number.isFinite(en)) return "";
  const si = Math.round(sid);
  const sj = Math.round(st);
  const sk = Math.round(en);
  return `${si}|${sj}|${sk}`;
}

/** Claves presentes en el panel tras renderizar (una fila gráfica ↔ un nodo enlazable). */
export function collectPaintedEntityKeysFromPanel(panel) {
  const ids = new Set();
  const occs = new Set();
  if (!panel) return { ids, occs };
  panel.querySelectorAll(".entity[data-id]").forEach((el) => {
    const v = el.getAttribute("data-id");
    if (v != null && v !== "") ids.add(String(v));
  });
  panel.querySelectorAll(".entity[data-occurrence]").forEach((el) => {
    const v = el.getAttribute("data-occurrence");
    if (v != null && v !== "") occs.add(String(v));
  });
  return { ids, occs };
}

/** ¿Existe en el DOM del panel un span para esta fila de datos (id u ocurrencia backend)? */
export function entityRowLinkedInPanel(row, keys) {
  if (!keys || (keys.ids.size === 0 && keys.occs.size === 0)) return true;
  const idStr = row?.id !== undefined && row?.id !== null ? String(row.id) : "";
  if (idStr && keys.ids.has(idStr)) return true;
  const occ = backendOccurrenceKey(row);
  return Boolean(occ && keys.occs.has(occ));
}

function sortEntitiesByDocPosition(entities) {
  return [...(entities || [])].sort((a, b) => {
    const ds = Number(a.sentence_id) - Number(b.sentence_id);
    if (ds !== 0) return ds;
    return Number(a.start) - Number(b.start);
  });
}

function buildHtmlFromRanges(text, ranges) {
  let result = "";
  let cursor = 0;
  for (const r of ranges) {
    if (r.start < cursor) continue;
    result += escapeHtml(text.slice(cursor, r.start));
    const _color = getColorForLabel(r.label);
    const sidNum = r.sentenceId != null ? Number(r.sentenceId) : NaN;
    const sentenceAttr = Number.isFinite(sidNum) ? ` data-sentence-id="${Math.round(sidNum)}"` : "";
    const startAttr = Number.isInteger(r.start) ? ` data-start="${r.start}"` : "";
    const endAttr = Number.isInteger(r.end) ? ` data-end="${r.end}"` : "";
    const occAttr = r.occurrenceKey
      ? ` data-occurrence="${escapeHtml(r.occurrenceKey)}"`
      : "";
    result += `<span class="entity" data-id="${escapeHtml(String(r.id))}"${sentenceAttr}${startAttr}${endAttr}${occAttr} data-entity-key="${escapeHtml(normalizeEntityKey(r.entity || text.slice(r.start, r.end)))}" data-label="${escapeHtml(String(r.label || ""))}" style="color:${_color}; border-bottom: 2px solid ${_color};">${escapeHtml(text.slice(r.start, r.end))}</span>`;
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
  const sentenceList = clusterSentenceRecords(data);
  return buildEntityParagraphs(cleanedText, sentenceList);
}

function entityAlreadyInParagraphs(ent, normalizedParagraphs) {
  const id = ent?.id;
  return normalizedParagraphs.some((p) =>
    (p.entities || []).some((e) => e.id === id),
  );
}

/**
 * Trozos de la frase modelo para enlazar párrafo aunque `cleaned_text` recorte o normalice distinto.
 */
function sentenceMatchAnchors(normalizedSentence) {
  const full = String(normalizedSentence || "").trim();
  if (!full) return [];
  const out = [];
  const push = (s) => {
    const t = String(s || "").trim();
    if (t.length < 2) return;
    if (!out.includes(t)) out.push(t);
  };
  push(full);
  if (full.length > 120) push(full.slice(0, 120));
  const words = full.split(/\s+/).filter((w) => w.length > 1);
  if (words.length >= 6) {
    push(words.slice(0, 6).join(" "));
    push(words.slice(-6).join(" "));
  } else if (words.length >= 2) {
    push(words.join(" "));
  }
  return out;
}

/** Prioridad: párrafos que contienen anclas de `sentence_text` (menos duplicados entre párrafos). */
function assignEntityOccurrenceBySentence(ent, normalizedParagraphs) {
  const sentenceText = String(ent?.sentence_text ?? "").trim();
  const normalizedSentence = sentenceText ? normalizeForParagraphMatch(sentenceText) : "";
  if (!normalizedSentence) return false;

  const anchors = sentenceMatchAnchors(normalizedSentence);
  if (!anchors.length) return false;

  let placed = false;
  normalizedParagraphs.forEach((paragraph) => {
    if (!anchors.some((a) => paragraph.normalized.includes(a))) return;
    placed = true;
    if (!paragraph.entities.some((existing) => existing.id === ent.id)) {
      paragraph.entities.push(ent);
    }
  });
  return placed;
}

/**
 * Si la frase no enlazó, colocar en el **primer** párrafo que contenga el término (una sola vez por id).
 */
function assignEntityOccurrenceFallback(ent, normalizedParagraphs) {
  if (entityAlreadyInParagraphs(ent, normalizedParagraphs)) return;

  const rawEntity = String(ent?.entity || "").trim();
  if (!rawEntity) return;

  const normalizedEntity = normalizeForParagraphMatch(rawEntity);
  if (!normalizedEntity) return;

  for (const paragraph of normalizedParagraphs) {
    if (!paragraph.normalized.includes(normalizedEntity)) continue;
    paragraph.entities.push(ent);
    return;
  }
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
    const placed = assignEntityOccurrenceBySentence(ent, normalizedParagraphs);
    if (!placed) assignEntityOccurrenceFallback(ent, normalizedParagraphs);
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
