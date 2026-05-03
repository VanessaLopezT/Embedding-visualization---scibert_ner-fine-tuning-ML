/**
 * tsneChartFrequency.js
 * Vista de frecuencia: un punto por palabra, tama?o por frecuencia.
 * Click en un agregado despliega ocurrencias individuales.
 */

import { getColorForLabel, ambosOriginFillColor, ambosSeriesLegendFill } from "./categoryColors.js?v=20260501h";
import {
  ENTITY_POINT_LABEL_COLOR,
  WORKSPACE_AXIS_TICK_COLOR,
  normalizeEntityAggregateKey,
} from "./chartAxisUtils.js?v=20260606_axis_auto";
import {
  backendOccurrenceKey,
  scrollPanelElementIntoView,
} from "./textPanel.js?v=20260603t";

let expandedEntityKey = null;
/** Igual que vista Original: min/max solo si el caller pasa `axisRange`; si no, ECharts escala al dato. */
let frequencyAxisRange = null;
const ARTICLE_LEGEND_WIDTH_TECH = "auto";
const ARTICLE_LEGEND_WIDTH_CMT = "56%";
const ARTICLE_LEGEND_WIDTH_WRAP = "52%";
const ARTICLE_LEGEND_TOP_PX = 76;
const ARTICLE_GRID_TOP_PX = 154;
let frequencyScaleOptions = {
  scaleMode: "article",
  globalReferenceMax: 30
};

export function initTSNEFrequencyChart(chart, data, axisRange = null, options = {}) {
  const safeData = Array.isArray(data) ? data : [];
  frequencyAxisRange = axisRange || null;
  frequencyScaleOptions = {
    scaleMode: options.scaleMode === "global" ? "global" : "article",
    globalReferenceMax: Number.isFinite(options.globalReferenceMax) && options.globalReferenceMax > 1
      ? options.globalReferenceMax
      : 30,
    combinedView: Boolean(options.combinedView),
  };
  // Validar si no hay datos de entidades
  if (safeData.length === 0) {
    chart.setOption({
      title: {
        text: "No se detectaron entidades",
        subtext: "El modelo no encontró entidades válidas en este texto",
        left: "center",
        top: "center",
        textStyle: {
          fontSize: 16,
          color: "#666",
          fontWeight: "normal"
        },
        subtextStyle: {
          fontSize: 12,
          color: "#999"
        }
      },
      series: [],
      legend: { show: false },
      xAxis: { show: false },
      yAxis: { show: false },
      toolbox: { show: false },
      dataZoom: []
    }, true);
    return;
  }

  // Limpiar título previo cuando hay datos
  chart.setOption({ title: { show: false } }, false);
  
  renderFrequency(chart, safeData);
  clearChartHoverState(chart);
  requestAnimationFrame(() => {
    if (chart && typeof chart.resize === "function") chart.resize();
  });

  chart.off("mouseover");
  chart.off("mouseout");
  chart.off("click");
  chart.off("legendselectchanged");

  chart.on("mouseover", (params) => {
    if (!params.data) return;
    const d = params.data;
    // Agregado con varias ocurrencias: no hay un solo span que resaltar.
    if (d.isAggregate && Number(d.frequency || 0) > 1) return;
    let target = d;
    if (d.isAggregate) {
      const only = Array.isArray(d.occurrences) ? d.occurrences[0] : null;
      if (!only) return;
      target = only;
    }
    highlightEntityInPanel(target);
  });

  chart.on("mouseout", () => {
    clearHighlightInPanel();
  });

  chart.on("click", (params) => {
    if (!params.data) return;
    if (params.data.isAggregate) {
      if (Number(params.data.frequency || 0) <= 1) {
        const only = Array.isArray(params.data.occurrences) ? params.data.occurrences[0] : null;
        if (only) highlightEntityInPanel(only);
        return;
      }
      try {
        chart.dispatchAction({ type: "downplay", seriesIndex: "all" });
      } catch (_) {}
      expandedEntityKey = expandedEntityKey === params.data.key ? null : params.data.key;
      renderFrequency(chart, safeData);
      clearChartHoverState(chart);
      return;
    }
    if (params.data.isOccurrence) {
      // Click en bolita pequena: seleccionar y colapsar (enlace por id o data-occurrence).
      highlightEntityInPanel(params.data);
      expandedEntityKey = null;
      try {
        chart.dispatchAction({ type: "downplay", seriesIndex: "all" });
      } catch (_) {}
      renderFrequency(chart, safeData);
      clearChartHoverState(chart);
      return;
    }
    if (params.data.id !== undefined) {
      highlightEntityInPanel(params.data);
    }
  });

}

export function resetFrequencyExpansion() {
  expandedEntityKey = null;
  frequencyAxisRange = null;
}

function clearChartHoverState(chart) {
  if (!chart || typeof chart.dispatchAction !== "function") return;
  try {
    chart.dispatchAction({ type: "downplay", seriesIndex: "all" });
    chart.dispatchAction({ type: "hideTip" });
  } catch (_) {
    // no-op
  }
}

function findOccurrenceNearClick(chart, params) {
  const list = Array.isArray(params?.data?.occurrences) ? params.data.occurrences : [];
  if (!list.length) return null;
  const pointer = getEventOffset(params?.event);
  if (!pointer) return null;
  return findOccurrenceNearPointer(chart, list, pointer, 10);
}

function findOccurrenceNearPointer(chart, list, pointer, hitRadius = 10) {
  let nearest = null;
  let bestDist = Number.POSITIVE_INFINITY;

  for (const occ of list) {
    const px = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [Number(occ.x || 0), Number(occ.y || 0)]);
    if (!Array.isArray(px) || px.length < 2) continue;
    const dx = px[0] - pointer.x;
    const dy = px[1] - pointer.y;
    const dist = Math.hypot(dx, dy);
    if (dist <= hitRadius && dist < bestDist) {
      bestDist = dist;
      nearest = occ;
    }
  }
  return nearest;
}

function getEventOffset(evt) {
  if (!evt) return null;
  if (Number.isFinite(evt.offsetX) && Number.isFinite(evt.offsetY)) {
    return { x: evt.offsetX, y: evt.offsetY };
  }
  const inner = evt.event;
  if (inner && Number.isFinite(inner.offsetX) && Number.isFinite(inner.offsetY)) {
    return { x: inner.offsetX, y: inner.offsetY };
  }
  return null;
}

function renderFrequency(chart, data) {
  const axisRange = frequencyAxisRange || null;
  // Siempre el dataset completo del modelo (solo dedupe por id/clave backend); no filtrar por DOM.
  const rows = dedupeFrequencyRows(data);
  const series = buildFrequencySeries(rows, expandedEntityKey, frequencyScaleOptions);
  const zoomState = readFrequencyDataZoomState(chart);

  const legendConfig = buildArticleLegendConfig(
    rows.map((point) => point?.label),
    { combinedView: Boolean(frequencyScaleOptions.combinedView) },
  );

  const option = {
    animation: true,
    animationDuration: 350,
    // Al expandir/colapsar un nodo no queremos desplazar el resto por tweening.
    animationDurationUpdate: 0,
    animationEasing: "cubicOut",
    animationEasingUpdate: "linear",
    tooltip: {
      show: true,
      formatter: function(p) {
        if (p.data && p.data.isAggregate) {
          let out = "<b>" + p.data.entity + "</b><br/>Tipo dominante: " + p.data.label +
            "<br/>Frecuencia: " + p.data.frequency;
          if (frequencyScaleOptions.combinedView && p.data.dominantOrigin) {
            const o = String(p.data.dominantOrigin).toLowerCase();
            const t = o === "tech" ? "TechBERT" : o === "cmt" ? "PatVetBERT" : "Ambos modelos";
            out += "<br/>Origen mayoritario: " + t;
          }
          return out;
        }
        return "<b>" + p.data.entity + "</b><br/>Tipo: " + (p.data.displayLabel || p.data.label);
      }
    },
    toolbox: {
      feature: {
        dataZoom: {},
        restore: {},
        saveAsImage: {}
      },
      right: 20,
      top: 20
    },
    legend: {
      top: ARTICLE_LEGEND_TOP_PX,
      left: "center",
      width: legendConfig.width,
      orient: "horizontal",
      textStyle: {
        fontSize: 12,
        color: ENTITY_POINT_LABEL_COLOR,
        fontWeight: 500
      },
      backgroundColor: legendConfig.backgroundColor,
      borderColor: legendConfig.borderColor,
      borderWidth: legendConfig.borderWidth,
      borderRadius: legendConfig.borderRadius,
      padding: legendConfig.padding,
      itemGap: 12,
      itemWidth: 11,
      itemHeight: 11,
    },
    grid: {
      left: 60,
      right: 30,
      bottom: 40,
      top: ARTICLE_GRID_TOP_PX,
      containLabel: true
    },
    backgroundColor: "#fafafa",
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: [0],
        start: zoomState?.x?.start ?? 0,
        end: zoomState?.x?.end ?? 100,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        moveOnMouseWheel: false,
        filterMode: "none",
        zoomLock: false
      },
      {
        type: "inside",
        yAxisIndex: [0],
        start: zoomState?.y?.start ?? 0,
        end: zoomState?.y?.end ?? 100,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        moveOnMouseWheel: false,
        filterMode: "none",
        zoomLock: false
      }
    ],
    xAxis: {
      type: "value",
      scale: true,
      ...(axisRange ? { min: axisRange.xMin, max: axisRange.xMax } : {}),
      name: "Dimensi\u00F3n 1",
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: {
        color: ENTITY_POINT_LABEL_COLOR,
        fontSize: 12,
        fontWeight: 600,
      },
      axisLabel: { color: WORKSPACE_AXIS_TICK_COLOR, fontSize: 11 },
      axisLine: { show: false, lineStyle: { color: "#000000" } },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: "#f0f0f0" }
      }
    },
    yAxis: {
      type: "value",
      scale: true,
      ...(axisRange ? { min: axisRange.yMin, max: axisRange.yMax } : {}),
      name: "Dimensi\u00F3n 2",
      nameLocation: "middle",
      nameGap: 40,
      nameTextStyle: {
        color: ENTITY_POINT_LABEL_COLOR,
        fontSize: 12,
        fontWeight: 600,
      },
      axisLabel: { color: WORKSPACE_AXIS_TICK_COLOR, fontSize: 11 },
      axisLine: { show: false, lineStyle: { color: "#000000" } },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: "#f0f0f0" }
      }
    },
    series
  };

  chart.setOption(option, true);
}

function readFrequencyDataZoomState(chart) {
  if (!chart || typeof chart.getOption !== "function") return null;
  try {
    const opt = chart.getOption();
    const dz = Array.isArray(opt?.dataZoom) ? opt.dataZoom : [];
    const x = dz.find((z) => Array.isArray(z?.xAxisIndex) && z.xAxisIndex.includes(0));
    const y = dz.find((z) => Array.isArray(z?.yAxisIndex) && z.yAxisIndex.includes(0));
    return {
      x: {
        start: Number.isFinite(Number(x?.start)) ? Number(x.start) : 0,
        end: Number.isFinite(Number(x?.end)) ? Number(x.end) : 100,
      },
      y: {
        start: Number.isFinite(Number(y?.start)) ? Number(y.start) : 0,
        end: Number.isFinite(Number(y?.end)) ? Number(y.end) : 100,
      },
    };
  } catch (_) {
    return null;
  }
}

function buildArticleLegendConfig(labels = [], opts = {}) {
  const combinedView = Boolean(opts.combinedView);
  const uniqueLabels = Array.from(new Set(labels.map(label => String(label || "").trim()).filter(Boolean)));
  const usesCmtLabels = labels.some(label => /\/| and |oncology|treatment/i.test(String(label || "")));
  if (usesCmtLabels && !combinedView) {
    return {
      width: uniqueLabels.length >= 7 ? ARTICLE_LEGEND_WIDTH_CMT : ARTICLE_LEGEND_WIDTH_TECH,
      backgroundColor: "rgba(255, 255, 255, 0.8)",
      borderColor: "#e0e0e0",
      borderWidth: 1,
      borderRadius: 4,
      padding: 7,
    };
  }

  return {
    width: uniqueLabels.length >= 7 ? ARTICLE_LEGEND_WIDTH_WRAP : ARTICLE_LEGEND_WIDTH_TECH,
    backgroundColor: "rgba(255, 255, 255, 0.8)",
    borderColor: "#e0e0e0",
    borderWidth: 1,
    borderRadius: 4,
    padding: 7,
  };
}

function _normOriginKey(origin) {
  const o = String(origin || "joint").toLowerCase();
  if (o === "tech") return "tech";
  if (o === "cmt") return "cmt";
  return "joint";
}

function _pickDominantOrigin(originCounts) {
  const tech = originCounts.tech || 0;
  const cmt = originCounts.cmt || 0;
  const joint = originCounts.joint || 0;
  const m = Math.max(tech, cmt, joint);
  if (m <= 0) return "joint";
  if (tech === m) return "tech";
  if (cmt === m) return "cmt";
  return "joint";
}

/** Evita la misma ocurrencia dos veces en el agregado (misma id o misma clave backend). */
function dedupeFrequencyRows(data) {
  const seen = new Set();
  const out = [];
  for (const p of Array.isArray(data) ? data : []) {
    const occ = backendOccurrenceKey(p);
    const k = occ || (p?.id !== undefined && p?.id !== null ? `id:${String(p.id)}` : null);
    if (k) {
      if (seen.has(k)) continue;
      seen.add(k);
    }
    out.push(p);
  }
  return out;
}

function buildFrequencySeries(rows, expandedKey, scaleOptions = {}) {
  const combinedView = Boolean(scaleOptions.combinedView);

  const aggregateMap = new Map();
  rows.forEach(p => {
    const raw = String(p.entity || "").trim();
    if (!raw) return;
    const key = normalizeEntityAggregateKey(raw);
    if (!aggregateMap.has(key)) {
      aggregateMap.set(key, {
        key,
        entity: raw,
        points: [],
        labelCounts: {},
        originCounts: { tech: 0, cmt: 0, joint: 0 },
      });
    }
    const bucket = aggregateMap.get(key);
    bucket.points.push(p);
    bucket.labelCounts[p.label] = (bucket.labelCounts[p.label] || 0) + 1;
    const ok = _normOriginKey(p.origin);
    bucket.originCounts[ok] += 1;
  });

  const aggregates = Array.from(aggregateMap.values()).map(item => {
    const count = item.points.length;
    const centroid = item.points.reduce((acc, p) => {
      acc.x += Number(p.x || 0);
      acc.y += Number(p.y || 0);
      return acc;
    }, { x: 0, y: 0 });
    centroid.x /= count;
    centroid.y /= count;

    const dominantLabel = Object.entries(item.labelCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || "TECHNIQUE";
    const dominantOrigin = _pickDominantOrigin(item.originCounts);
    return {
      key: item.key,
      entity: item.entity,
      frequency: count,
      label: dominantLabel,
      dominantOrigin,
      value: [centroid.x, centroid.y],
      occurrences: item.points
    };
  });

  const frequencies = aggregates.map(a => a.frequency);
  const maxFreq = frequencies.length ? Math.max(...frequencies) : 1;
  const scaleMode = scaleOptions.scaleMode === "global" ? "global" : "article";
  const globalReferenceMax = Number.isFinite(scaleOptions.globalReferenceMax) && scaleOptions.globalReferenceMax > 1
    ? scaleOptions.globalReferenceMax
    : 30;
  const referenceMax = scaleMode === "global"
    ? Math.max(2, globalReferenceMax)
    : Math.max(2, maxFreq);

  const sizeFromFrequency = (frequency) => {
    // Escala dinamica para cualquier rango de frecuencias:
    // - 1 se mantiene como referencia visual minima
    // - crecimiento logaritmico para evitar que outliers aplasten valores bajos
    // - exponente < 1 para separar mejor frecuencias bajas (2, 3, 4...)
    if (frequency <= 1) return 16;
    if (referenceMax <= 1) return 16;

    const minRepeated = 2;
    const minSize = 20;
    const maxSize = 60;
    const alpha = 0.65;

    if (referenceMax <= minRepeated) return minSize;

    const logMin = Math.log(minRepeated);
    const logMax = Math.log(referenceMax);
    const logF = Math.log(Math.max(frequency, minRepeated));
    const t = (logF - logMin) / Math.max(logMax - logMin, 1e-9);
    const eased = Math.pow(Math.max(0, Math.min(1, t)), alpha);
    return minSize + (maxSize - minSize) * eased;
  };

  const groupedByLabel = {};
  aggregates.forEach(item => {
    const groupKey = item.label;
    if (!groupedByLabel[groupKey]) groupedByLabel[groupKey] = [];
    const isExpandedAggregate = Boolean(expandedKey) && item.key === expandedKey;
    const baseSize = sizeFromFrequency(item.frequency);
    if (!isExpandedAggregate) {
      groupedByLabel[groupKey].push({
        ...item,
        isAggregate: true,
        symbolSize: baseSize,
        symbol: "circle",
        itemStyle: combinedView ? {
          color: ambosOriginFillColor(item.label, item.dominantOrigin),
          borderColor: "#ffffff",
          borderWidth: 1,
          opacity: 1,
        } : undefined,
        emphasis: {
          focus: "series",
          scale: true,
        }
      });
    }
  });

  if (expandedKey) {
    const expanded = aggregates.find(item => item.key === expandedKey);
    if (expanded && expanded.occurrences.length) {
      if (!groupedByLabel[expanded.label]) groupedByLabel[expanded.label] = [];
      const seenExp = new Set();
      expanded.occurrences.forEach((p) => {
        const occ = backendOccurrenceKey(p);
        const kid = p?.id !== undefined && p?.id !== null ? `id:${String(p.id)}` : null;
        const ek = occ || kid;
        if (ek) {
          if (seenExp.has(ek)) return;
          seenExp.add(ek);
        }
        groupedByLabel[expanded.label].push({
          value: [Number(p.x || 0), Number(p.y || 0)],
          id: p.id,
          entity: p.entity,
          label: p.label,
          displayLabel: expanded.label,
          sentence_text: p.sentence_text,
          text_index: p.text_index,
          sentence_id: p.sentence_id,
          start: p.start,
          end: p.end,
          isOccurrence: true,
          parentKey: expanded.key,
          symbolSize: 12,
          symbol: "circle",
          itemStyle: combinedView ? {
            color: ambosOriginFillColor(p.label, p.origin),
            borderColor: "#ffffff",
            borderWidth: 1,
            opacity: 1,
          } : undefined,
          z: 5,
          emphasis: {
            focus: "series",
            scale: true,
          }
        });
      });
    }
  }

  return Object.keys(groupedByLabel).map((label) => ({
    id: `freq-${label}`,
    name: label,
    type: "scatter",
    data: groupedByLabel[label],
    symbolSize: (_value, params) => params?.data?.symbolSize ?? 16,
    symbol: "circle",
    itemStyle: combinedView ? {
      opacity: 1,
      color: ambosSeriesLegendFill(
        label,
        groupedByLabel[label].map((d) => d.dominantOrigin ?? d.origin ?? "joint"),
      ),
    } : {
      color: getColorForLabel(label),
      opacity: 1,
      borderColor: "#ffffff",
      borderWidth: 1
    },
    label: {
      show: true,
      formatter: p => {
        if (p?.data?.isOccurrence) return "";
        return `${p.data.entity} (${p.data.frequency})`;
      },
      position: "top",
      distance: 6,
      fontSize: 10,
      color: ENTITY_POINT_LABEL_COLOR,
      fontWeight: 500,
    },
    emphasis: {
      focus: "series",
      scale: true,
    }
  }));
}

function highlightEntityInPanel(datum) {
  clearHighlightInPanel();
  const entityEl = findEntityElement(datum);
  if (entityEl) {
    entityEl.classList.add("highlighted");
    const panel = document.getElementById("text-panel");
    if (panel) scrollPanelElementIntoView(panel, entityEl);
  }
}

/**
 * Si hay varias marcas iguales en la misma frase: desambiguar por etiqueta,
 * luego por data-occurrence (misma clave que la fila del gráfico).
 */
function findEntityElementBySentenceEntityKey(panel, datum) {
  const sidRaw = datum?.sentence_id;
  if (sidRaw == null || !Number.isFinite(Number(sidRaw))) return null;
  const sidAttr = String(Math.round(Number(sidRaw)));
  const entityKey = normalizeEntityKey(datum?.entity || "");
  if (!entityKey) return null;
  const label = String(datum?.label ?? "").trim();
  const occWant = backendOccurrenceKey(datum);
  const hits = [];
  for (const el of panel.querySelectorAll(".entity[data-entity-key]")) {
    if (el.getAttribute("data-sentence-id") !== sidAttr) continue;
    if (el.getAttribute("data-entity-key") !== entityKey) continue;
    hits.push(el);
  }
  if (hits.length === 0) return null;

  const matchOcc = (el) => {
    if (!occWant) return false;
    const attr = el.getAttribute("data-occurrence");
    if (!attr) return false;
    const domNorm = parseOccurrenceKeyTuple(attr);
    return domNorm === occWant || attr === occWant;
  };

  if (occWant) {
    const byOcc = hits.filter(matchOcc);
    if (byOcc.length === 1) return byOcc[0];
  }

  if (hits.length === 1) return hits[0];
  if (hits.length > 1 && label) {
    const filtered = hits.filter((el) => String(el.getAttribute("data-label") || "").trim() === label);
    if (filtered.length === 1) return filtered[0];
    if (occWant) {
      const fo = filtered.filter(matchOcc);
      if (fo.length === 1) return fo[0];
    }
  }
  return null;
}

function parseOccurrenceKeyTuple(attr) {
  const s = String(attr || "").trim();
  const parts = s.split("|");
  if (parts.length !== 3) return null;
  const a = Number(parts[0]);
  const b = Number(parts[1]);
  const c = Number(parts[2]);
  if (!Number.isFinite(a) || !Number.isFinite(b) || !Number.isFinite(c)) return null;
  return `${Math.round(a)}|${Math.round(b)}|${Math.round(c)}`;
}

function findEntityElement(datum) {
  const panel = document.getElementById("text-panel");
  if (!panel) return null;

  const entityText = datum?.entity || "";
  const idStr = datum?.id !== undefined && datum?.id !== null ? String(datum.id) : "";
  const occ = backendOccurrenceKey(datum);

  if (idStr) {
    const idHits = [...panel.querySelectorAll(".entity[data-id]")].filter(
      (el) => el.getAttribute("data-id") === idStr,
    );
    if (idHits.length === 1) return idHits[0];
    if (idHits.length > 1 && occ) {
      for (const el of idHits) {
        const attr = el.getAttribute("data-occurrence");
        if (!attr) continue;
        const domNorm = parseOccurrenceKeyTuple(attr);
        if (domNorm === occ || attr === occ) return el;
      }
    }
  }

  if (occ) {
    for (const el of panel.querySelectorAll(".entity[data-occurrence]")) {
      const attr = el.getAttribute("data-occurrence");
      if (!attr) continue;
      if (attr === occ) return el;
      const domNorm = parseOccurrenceKeyTuple(attr);
      if (domNorm && domNorm === occ) return el;
    }
  }

  const bySentence = findEntityElementBySentenceEntityKey(panel, datum);
  if (bySentence) return bySentence;

  // Solo si hay una sola marca con ese texto en todo el panel (evita varias "DNA" → la primera).
  const key = normalizeEntityKey(entityText);
  if (!key) return null;
  const keyHits = [...panel.querySelectorAll(".entity[data-entity-key]")].filter(
    (el) => el.getAttribute("data-entity-key") === key,
  );
  if (keyHits.length === 1) return keyHits[0];
  return null;
}

function normalizeEntityKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[“”"']/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function clearHighlightInPanel() {
  document.querySelectorAll(".entity.highlighted").forEach(el => {
    el.classList.remove("highlighted");
  });
}




