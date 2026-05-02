/**
 * tsneChart.js
 * Gestiona la visualizaciÃ³n base de la grÃ¡fica t-SNE con ECharts.
 */

import { getColorForLabel, ambosOriginFillColor, ambosSeriesLegendFill } from "./categoryColors.js?v=20260501h";

let globalChart = null;
const ARTICLE_LEGEND_WIDTH_TECH = "auto";
const ARTICLE_LEGEND_WIDTH_CMT = "56%";
const ARTICLE_LEGEND_WIDTH_WRAP = "52%";
/** Leyenda bajo los overlays HTML (Escala / Mostrar), no encima en z-order del lienzo. */
const ARTICLE_LEGEND_TOP_PX = 76;
const ARTICLE_GRID_TOP_PX = 154;

export function initTSNEChart(chart, data, axisRange = null, options = {}) {
  const combinedView = Boolean(options.combinedView);
  globalChart = chart;
  
  // Validar si no hay datos de entidades
  if (!Array.isArray(data) || data.length === 0) {
    chart.setOption({
      title: {
        text: "No se detectaron entidades",
        subtext: "No se encontraron entidades válidas en este texto para el modelo seleccionado",
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
      yAxis: { show: false }
    }, true);
    return;
  }
  
  const legendConfig = buildArticleLegendConfig(
    data.map((point) => point?.label),
    { combinedView },
  );
  
  // Limpiar título previo cuando hay datos
  chart.setOption({ title: { show: false } }, false);
  
  const groups = {};
  data.forEach(p => {
    const gk = p.label || "UNKNOWN";
    if (!groups[gk]) groups[gk] = [];
    const row = {
      value: [p.x, p.y],
      entity: p.entity,
      label: p.label,
      origin: p.origin,
      text_index: p.text_index,
      id: p.id,
      sentence_text: p.sentence_text,
    };
    if (combinedView) {
      row.itemStyle = {
        color: ambosOriginFillColor(p.label, p.origin),
        borderColor: "#ffffff",
        borderWidth: 1,
      };
    }
    groups[gk].push(row);
  });

  const groupKeys = Object.keys(groups);

  const series = groupKeys.map((groupKey) => ({
    name: groupKey,
    type: "scatter",
    data: groups[groupKey],
    symbolSize: 16,
    symbol: "circle",
    itemStyle: combinedView ? {
      color: ambosSeriesLegendFill(groupKey, groups[groupKey].map((p) => p.origin)),
      borderColor: "#ffffff",
      borderWidth: 1,
    } : {
      color: getColorForLabel(groupKey),
      borderColor: "#ffffff",
      borderWidth: 1,
    },

    label: {
      show: true,
      formatter: p => p.data.entity,
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
  const option = {
    animation: true,
    animationDuration: 350,
    animationDurationUpdate: 350,
    animationEasing: "cubicOut",
    tooltip: {
      show: true,
      formatter: function(p) {
        const origin = p?.data?.origin;
        const extra = combinedView && origin
          ? "<br/>Origen: " +
            (String(origin).toLowerCase() === "tech" ? "TechBERT"
              : String(origin).toLowerCase() === "cmt" ? "PatVetBERT" : "Ambos modelos")
          : "";
        return "<b>" + p.data.entity + "</b><br/>" + "Tipo: " + p.seriesName + extra;
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

  chart.off("mouseover");
  chart.off("mouseout");
  chart.on("mouseover", (params) => {
    if (params.data && params.data.id !== undefined) {
      highlightEntityInPanel(params.data.id, params.data.entity);
    }
  });

  chart.on("mouseout", () => {
    clearHighlightInPanel();
  });

  window.addEventListener("resize", () => chart.resize());
}

function highlightEntityInPanel(id, entityText = "") {
  const entityEl = findEntityElement(id, entityText);
  if (entityEl) {
    entityEl.classList.add("highlighted");
    const panel = document.getElementById("text-panel");
    if (panel) {
      const targetTop = entityEl.offsetTop - (panel.clientHeight / 2) + (entityEl.offsetHeight / 2);
      panel.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
    }
  }
}

function findEntityElement(id, entityText = "") {
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

function buildArticleLegendConfig(labels = [], opts = {}) {
  const combinedView = Boolean(opts.combinedView);
  const uniqueLabels = Array.from(new Set(labels.map(label => String(label || "").trim()).filter(Boolean)));
  const usesCmtLabels = labels.some(label => /\/| and |oncology|treatment/i.test(String(label || "")));
  /** En «ambos» la mezcla dispara uso de anchos CMT y encoge el plot; misma geometría que vistas por modelo único típicas. */
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

export function createTSNEChart(domElement, data) {
  const chart = echarts.init(domElement);
  initTSNEChart(chart, data);
}

export function highlightPoint(id) {
  if (!globalChart) return;

  const option = globalChart.getOption();
  option.series.forEach(series => {
    series.data.forEach((point) => {
      if (point.id === id) {
        if (!series.itemStyle) series.itemStyle = {};
        series.itemStyle.color = "#ffff00";
        series.itemStyle.opacity = 1;
      }
    });
  });
  globalChart.setOption(option, { notMerge: false });
}

export function clearHighlight() {
  if (!globalChart) return;
  globalChart.setOption(globalChart.getOption(), { notMerge: false });
}

