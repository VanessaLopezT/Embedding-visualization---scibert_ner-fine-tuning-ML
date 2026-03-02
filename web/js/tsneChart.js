/**
 * tsneChart.js
 * Gestiona la visualizaciÃ³n base de la grÃ¡fica t-SNE con ECharts.
 */

import { CATEGORY_COLORS } from "./categoryColors.js";

let globalChart = null;

export function initTSNEChart(chart, data, axisRange = null) {
  globalChart = chart;
  // Agrupar los puntos por su etiqueta para crear series separadas
  const groups = {};
  data.forEach(p => {
    if (!groups[p.label]) groups[p.label] = [];

    groups[p.label].push({

      value: [p.x, p.y],
      
      entity: p.entity,
      label: p.label,
      text_index: p.text_index,
      id: p.id,
      sentence_text: p.sentence_text
    });
  });

  const series = Object.keys(groups).map(label => ({
    name: label,
    type: "scatter",
    data: groups[label],
    symbolSize: 16,
    itemStyle: {
      color: CATEGORY_COLORS[label] || "#666"
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
      itemStyle: {
        borderColor: "#333",
        borderWidth: 2
      }
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
        return "<b>" + p.data.entity + "</b><br/>" + "Tipo: " + p.seriesName;
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

  chart.off("mouseover");
  chart.off("mouseout");
  chart.on("mouseover", (params) => {
    if (params.data && params.data.id !== undefined) {
      highlightEntityInPanel(params.data.id);
    }
  });

  chart.on("mouseout", () => {
    clearHighlightInPanel();
  });

  window.addEventListener("resize", () => chart.resize());
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

