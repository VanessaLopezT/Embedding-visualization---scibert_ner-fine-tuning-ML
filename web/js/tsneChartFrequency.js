/**
 * tsneChartFrequency.js
 * Vista de frecuencia: un punto por palabra, tama?o por frecuencia.
 * Click en un agregado despliega ocurrencias individuales.
 */

import { CATEGORY_COLORS } from "./categoryColors.js";

let expandedEntityKey = null;
let frequencyAxisRange = null;
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
      : 30
  };
  const safeData = Array.isArray(data) ? data : [];
  renderFrequency(chart, safeData);
  clearChartHoverState(chart);

  chart.off("mouseover");
  chart.off("mouseout");
  chart.off("click");

  chart.on("mouseover", (params) => {
    if (!params.data) return;
    if (params.data.id !== undefined) {
      highlightEntityInPanel(params.data.id);
      return;
    }
    if (params.data.isAggregate && Number(params.data.frequency || 0) <= 1) {
      const only = Array.isArray(params.data.occurrences) ? params.data.occurrences[0] : null;
      if (only && only.id !== undefined) {
        highlightEntityInPanel(only.id);
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
          highlightEntityInPanel(only.id);
        }
        return;
      }
      // Si ya esta expandida y el click cae sobre una bolita interna,
      // priorizar la bolita interna en lugar de colapsar la grande.
      if (expandedEntityKey && expandedEntityKey === params.data.key) {
        const hitOccurrence = findOccurrenceNearClick(chart, params);
        if (hitOccurrence && hitOccurrence.id !== undefined) {
          highlightEntityInPanel(hitOccurrence.id);
          return;
        }
      }
      expandedEntityKey = expandedEntityKey === params.data.key ? null : params.data.key;
      renderFrequency(chart, safeData);
      clearChartHoverState(chart);
      return;
    }
    if (params.data.isOccurrence) {
      // Click en bolita pequena: seleccionar, no colapsar.
      if (params.data.id !== undefined) {
        highlightEntityInPanel(params.data.id);
      }
      return;
    }
    if (params.data.id !== undefined) {
      highlightEntityInPanel(params.data.id);
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
  const series = buildFrequencySeries(data, expandedEntityKey, frequencyScaleOptions);
  const axisRange = frequencyAxisRange || getCurrentAxisRange(chart);

  const option = {
    animation: true,
    animationDuration: 350,
    animationDurationUpdate: 350,
    animationEasing: "cubicOut",
    tooltip: {
      show: true,
      formatter: function(p) {
        if (p.data && p.data.isAggregate) {
          return "<b>" + p.data.entity + "</b><br/>Tipo dominante: " + p.data.label +
                 "<br/>Frecuencia: " + p.data.frequency + "<br/>Click para ver ocurrencias";
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
      top: 10,
      left: "center",
      orient: "horizontal",
      textStyle: {
        fontSize: 13,
        color: "#333",
        fontWeight: 500
      },
      backgroundColor: "rgba(255, 255, 255, 0.8)",
      borderColor: "#e0e0e0",
      borderWidth: 1,
      borderRadius: 4,
      padding: 8,
      itemGap: 25,
      itemWidth: 12,
      itemHeight: 12
    },
    grid: {
      left: 60,
      right: 30,
      bottom: 40,
      top: 70,
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

function getCurrentAxisRange(chart) {
  if (!chart || typeof chart.getModel !== "function") return null;
  try {
    const model = chart.getModel();
    const xAxis = model.getComponent("xAxis", 0)?.axis;
    const yAxis = model.getComponent("yAxis", 0)?.axis;
    if (!xAxis || !yAxis) return null;
    const [xMin, xMax] = xAxis.scale.getExtent();
    const [yMin, yMax] = yAxis.scale.getExtent();
    if (![xMin, xMax, yMin, yMax].every(Number.isFinite)) return null;
    return { xMin, xMax, yMin, yMax };
  } catch (_) {
    return null;
  }
}

function buildFrequencySeries(data, expandedKey, scaleOptions = {}) {
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
        labelCounts: {}
      });
    }
    const bucket = aggregateMap.get(key);
    bucket.points.push(p);
    bucket.labelCounts[p.label] = (bucket.labelCounts[p.label] || 0) + 1;
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
    return {
      key: item.key,
      entity: item.entity,
      frequency: count,
      label: dominantLabel,
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
    if (frequency <= 1) return 9;
    if (referenceMax <= 1) return 9;

    const minRepeated = 2;
    const minSize = 16;
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
    if (!groupedByLabel[item.label]) groupedByLabel[item.label] = [];
    const isExpandedAggregate = Boolean(expandedKey) && item.key === expandedKey;
    const baseSize = sizeFromFrequency(item.frequency);
    const expandedSize = Math.max(14, baseSize * 0.55);
    groupedByLabel[item.label].push({
      ...item,
      isAggregate: true,
      symbolSize: isExpandedAggregate ? expandedSize : baseSize,
      // Mantenerla visible para colapsar, pero menos invasiva al expandir.
      symbol: "circle",
      itemStyle: isExpandedAggregate
        ? { opacity: 0.28, borderWidth: 2 }
        : undefined,
      // Solo freq=1 provoca foco por categoria (como modo original).
      emphasis: item.frequency <= 1
        ? {
            focus: "series",
            scale: true,
            itemStyle: { borderColor: "#333", borderWidth: 2 }
          }
        : {
            scale: true,
            itemStyle: { borderColor: "#333", borderWidth: 2 }
          }
    });
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
          isOccurrence: true,
          parentKey: expanded.key,
          symbolSize: 9,
          z: 5,
          emphasis: {
            focus: "series",
            scale: true,
            itemStyle: { borderColor: "#222", borderWidth: 2 }
          }
        });
      });
    }
  }

  return Object.keys(groupedByLabel).map(label => ({
    id: `freq-${label}`,
    name: label,
    type: "scatter",
    data: groupedByLabel[label],
    symbolSize: (_value, params) => params?.data?.symbolSize ?? 16,
    itemStyle: {
      color: CATEGORY_COLORS[label] || "#666",
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
      scale: true,
      itemStyle: {
        borderColor: "#333",
        borderWidth: 2
      }
    }
  }));
}

function highlightEntityInPanel(id) {
  const entityEl = document.querySelector(`[data-id="${id}"]`);
  if (entityEl) {
    entityEl.classList.add("highlighted");
    const panel = document.getElementById("text-panel");
    if (panel) {
      const targetTop = entityEl.offsetTop - (panel.clientHeight / 2) + (entityEl.offsetHeight / 2);
      panel.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
    }
  }
}

function clearHighlightInPanel() {
  document.querySelectorAll(".entity.highlighted").forEach(el => {
    el.classList.remove("highlighted");
  });
}




