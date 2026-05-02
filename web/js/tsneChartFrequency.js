/**
 * tsneChartFrequency.js
 * Vista de frecuencia: un punto por palabra, tama?o por frecuencia.
 * Click en un agregado despliega ocurrencias individuales.
 */

import { getColorForLabel, ambosOriginFillColor, ambosSeriesLegendFill } from "./categoryColors.js?v=20260501h";

let expandedEntityKey = null;
/** Igual que vista Original (`tsneChart.js`): solo min/max si el caller pasa `axisRange`; si no, ECharts escala solo. */
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
  frequencyAxisRange = axisRange || null;
  frequencyScaleOptions = {
    scaleMode: options.scaleMode === "global" ? "global" : "article",
    globalReferenceMax: Number.isFinite(options.globalReferenceMax) && options.globalReferenceMax > 1
      ? options.globalReferenceMax
      : 30,
    combinedView: Boolean(options.combinedView),
  };
  const safeData = Array.isArray(data) ? data : [];

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
    if (params.data.id !== undefined) {
      highlightEntityInPanel(params.data);
      return;
    }
    if (params.data.isAggregate && Number(params.data.frequency || 0) <= 1) {
      const only = Array.isArray(params.data.occurrences) ? params.data.occurrences[0] : null;
      if (only && only.id !== undefined) {
        highlightEntityInPanel(only);
      }
    }
  });

  chart.on("mouseout", () => {
    clearHighlightInPanel();
  });

  chart.on("click", (params) => {
    if (!params.data) return;
    if (params.data.isAggregate) {
      if (Number(params.data.frequency || 0) <= 1) {
        const only = Array.isArray(params.data.occurrences) ? params.data.occurrences[0] : null;
        if (only && only.id !== undefined) {
          highlightEntityInPanel(only);
        }
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
      // Click en bolita pequena: seleccionar y colapsar.
      if (params.data.id !== undefined) {
        highlightEntityInPanel(params.data);
      }
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
  const series = buildFrequencySeries(data, expandedEntityKey, frequencyScaleOptions);

  const legendConfig = buildArticleLegendConfig(
    data.map((point) => point?.label),
    { combinedView: Boolean(frequencyScaleOptions.combinedView) },
  );

  const option = {
    animation: true,
    animationDuration: 350,
    animationDurationUpdate: 350,
    animationEasing: "cubicOut",
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
        color: "#333",
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
        start: 0,
        end: 100,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        moveOnMouseWheel: false,
        filterMode: "none",
        zoomLock: false
      },
      {
        type: "inside",
        yAxisIndex: [0],
        start: 0,
        end: 100,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        moveOnMouseWheel: false,
        filterMode: "none",
        zoomLock: false
      }
    ],
    xAxis: {
      type: "value",
      ...(axisRange ? { min: axisRange.xMin, max: axisRange.xMax } : {}),
      name: "Dimensi\u00F3n 1",
      nameLocation: "middle",
      nameGap: 30,
      axisLine: { show: false, lineStyle: { color: "#000000" } },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: "#f0f0f0" }
      }
    },
    yAxis: {
      type: "value",
      ...(axisRange ? { min: axisRange.yMin, max: axisRange.yMax } : {}),
      name: "Dimensi\u00F3n 2",
      nameLocation: "middle",
      nameGap: 40,
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

function buildFrequencySeries(data, expandedKey, scaleOptions = {}) {
  const combinedView = Boolean(scaleOptions.combinedView);
  const aggregateMap = new Map();
  data.forEach(p => {
    const raw = String(p.entity || "").trim();
    if (!raw) return;
    const key = raw.toLowerCase().replace(/\s+/g, " ");
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
      expanded.occurrences.forEach((p) => {
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
          symbolSize: 9,
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
      color: "#333",
      fontWeight: "normal"
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
    if (panel) {
      const targetTop = entityEl.offsetTop - (panel.clientHeight / 2) + (entityEl.offsetHeight / 2);
      panel.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
    }
  }
}

function findEntityElement(datum) {
  const id = datum?.id;
  const entityText = datum?.entity || "";
  const sentenceId = Number(datum?.sentence_id);
  const start = Number(datum?.start);
  const end = Number(datum?.end);

  if (Number.isInteger(sentenceId) && Number.isInteger(start) && Number.isInteger(end)) {
    const exact = document.querySelector(
      `[data-sentence-id="${sentenceId}"][data-start="${start}"][data-end="${end}"]`
    );
    if (exact) return exact;
  }

  let entityEl = document.querySelector(`[data-id="${id}"]`);
  if (entityEl) return entityEl;
  const key = normalizeEntityKey(entityText);
  if (!key) return null;
  return document.querySelector(`[data-entity-key="${key}"]`);
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




