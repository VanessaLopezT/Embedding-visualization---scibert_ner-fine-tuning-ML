/**
 * tsneChartFrequency.js
 * Vista de frecuencia: un punto por palabra, tamaño por frecuencia.
 * Click en un agregado despliega ocurrencias individuales.
 */

import { CATEGORY_COLORS } from "./categoryColors.js";

let expandedEntityKey = null;
let frequencyAxisRange = null;

export function initTSNEFrequencyChart(chart, data, axisRange = null) {
  frequencyAxisRange = axisRange || null;
  const safeData = Array.isArray(data) ? data : [];
  renderFrequency(chart, safeData);

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
      expandedEntityKey = expandedEntityKey === params.data.key ? null : params.data.key;
      renderFrequency(chart, safeData);
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

function renderFrequency(chart, data) {
  const series = buildFrequencySeries(data, expandedEntityKey);
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
      name: "Dimensión 1",
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
      name: "Dimensión 2",
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

function buildFrequencySeries(data, expandedKey) {
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
  const minFreq = frequencies.length ? Math.min(...frequencies) : 1;
  const maxFreq = frequencies.length ? Math.max(...frequencies) : 1;
  const sizeFromFrequency = (frequency) => {
     // Frecuencia 1: mismo tamaño que una ocurrencia individual
    if (frequency <= 1) return 9;
    if (maxFreq <= 1) return 9;
    const minRepeated = Math.max(2, minFreq);
    if (maxFreq === minRepeated) return 26;
    const t = (frequency - minRepeated) / (maxFreq - minRepeated);
    return 20 + (t * 18);
  };

  const groupedAggregates = {};
  aggregates.forEach(item => {
    if (!groupedAggregates[item.label]) groupedAggregates[item.label] = [];
    groupedAggregates[item.label].push({
      ...item,
      isAggregate: true,
      symbolSize: sizeFromFrequency(item.frequency)
    });
  });

  const aggregateSeries = Object.keys(groupedAggregates).map(label => ({
    name: label,
    type: "scatter",
    data: groupedAggregates[label],
    symbolSize: (_value, params) => params?.data?.symbolSize ?? 16,
    itemStyle: {
      color: CATEGORY_COLORS[label] || "#666",
      opacity: 1,
      borderColor: "#ffffff",
      borderWidth: 1
    },
    label: {
      show: true,
      formatter: p => `${p.data.entity} (${p.data.frequency})`,
      position: "top",
      distance: 6,
      fontSize: 10,
      color: "#333",
      fontWeight: "normal"
    },
    emphasis: {
      focus: "series",
      scale: true,
      itemStyle: {
        borderColor: "#333",
        borderWidth: 2
      }
    }
  }));

  if (!expandedKey) return aggregateSeries;

  const expanded = aggregates.find(item => item.key === expandedKey);
  if (!expanded || !expanded.occurrences.length) return aggregateSeries;

  const occurrences = [];
  expanded.occurrences.forEach((p) => {
    const occurrencePoint = {
      value: [
        Number(p.x || 0),
        Number(p.y || 0)
      ],
      id: p.id,
      entity: p.entity,
      label: p.label,
      displayLabel: expanded.label,
      sentence_text: p.sentence_text,
      text_index: p.text_index,
      isOccurrence: true
    };
    occurrences.push(occurrencePoint);
  });

  const occurrenceSeries = [{
    name: expanded.label,
    type: "scatter",
    data: occurrences,
    symbolSize: 9,
    itemStyle: {
      color: CATEGORY_COLORS[expanded.label] || "#666",
      opacity: 1,
      borderColor: "#ffffff",
      borderWidth: 1
    },
    label: { show: false },
    emphasis: {
      focus: "self",
      scale: true,
      itemStyle: {
        borderColor: "#222",
        borderWidth: 2
      }
    }
  }];

  return [...aggregateSeries, ...occurrenceSeries];
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




