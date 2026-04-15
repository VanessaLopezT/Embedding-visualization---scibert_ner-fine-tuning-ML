import { getColorForLabel } from "./categoryColors.js";

let expandedEntityKey = null;

const WORKSPACE_LEGEND_WIDTH = "52%";

export function initWorkspaceAggregateChart(chart, payload = {}) {
  const points = Array.isArray(payload?.points) ? payload.points : [];

  renderWorkspaceAggregate(chart, points);
  requestAnimationFrame(() => {
    chart.resize();
  });
  clearChartHoverState(chart);

  chart.off("click");
  chart.off("mouseout");

  chart.on("click", (params) => {
    const data = params?.data;
    if (!data) return;

    if (data.isAggregate) {
      const canExpand = Array.isArray(data.article_breakdown) && data.article_breakdown.length > 0;

      if (!canExpand) {
        if (expandedEntityKey !== null) {
          expandedEntityKey = null;
          renderWorkspaceAggregate(chart, points);
          clearChartHoverState(chart);
        }
        return;
      }

      expandedEntityKey = expandedEntityKey === data.key ? null : data.key;
      renderWorkspaceAggregate(chart, points);
      clearChartHoverState(chart);
      return;
    }

    if (data.isContribution) {
      expandedEntityKey = null;

      // 🔥 fuerza repaint limpio
      chart.dispatchAction({
        type: 'downplay',
        seriesIndex: 'all'
      });

      renderWorkspaceAggregate(chart, points);
    }
  });

  chart.on("mouseout", () => {
    clearChartHoverState(chart);
  });
}

export function resetWorkspaceAggregateExpansion() {
  expandedEntityKey = null;
}

function renderWorkspaceAggregate(chart, points) {
  // Validar si no hay datos de entidades
  if (!Array.isArray(points) || points.length === 0) {
    chart.setOption({
      title: {
        text: "No se detectaron entidades",
        subtext: "El workspace no contiene entidades válidas para el modelo seleccionado",
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
  
  const series = buildSeries(points, expandedEntityKey);

  chart.setOption({
    animation: true,
    animationDuration: 350,
    animationDurationUpdate: 350,
    animationEasing: "cubicOut",
    tooltip: {
      show: true,
      formatter(params) {
        const data = params?.data || {};

        if (data.isContribution) {
          return [
            `<b>${escapeHtml(data.entity || "")}</b>`,
            `Articulo: ${escapeHtml(data.articleName || "")}`,
            `Frecuencia en articulo: ${Number(data.frequency || 0)}`,
            `Tipo: ${escapeHtml(data.label || "UNKNOWN")}`,
          ].join("<br/>");
        }

        return [
          `<b>${escapeHtml(data.entity || "")}</b>`,
          `Tipo: ${escapeHtml(data.label || "UNKNOWN")}`,
          `Frecuencia total: ${Number(data.frequency || 0)}`,
          `Articulos del workspace: ${Number(data.articleCount || 0)}`,
        ].join("<br/>");
      },
    },
    toolbox: {
      feature: {
        dataZoom: {},
        restore: {
          onclick: () => {
            expandedEntityKey = null;
          },
        },
        saveAsImage: {},
      },
      right: 20,
      top: 20,
    },
    legend: {
      type: "plain",
      top: 4,
      left: "center",
      width: WORKSPACE_LEGEND_WIDTH,
      orient: "horizontal",
      textStyle: {
        fontSize: 12,
        color: "#333",
        fontWeight: 500,
      },
      backgroundColor: "rgba(255, 255, 255, 0.9)",
      borderColor: "#e0e0e0",
      borderWidth: 1,
      borderRadius: 4,
      padding: 8,
      itemGap: 12,
      itemWidth: 12,
      itemHeight: 12,
    },
    grid: {
      left: 60,
      right: 30,
      bottom: 40,
      top: 78,
      containLabel: true,
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
      },
    ],
    xAxis: {
      type: "value",
      name: "Dimension 1",
      nameLocation: "middle",
      nameGap: 30,
      axisLabel: {
        formatter(value) {
          return Number(value || 0).toFixed(1);
        },
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { color: "#f0f0f0" } },
    },
    yAxis: {
      type: "value",
      name: "Dimension 2",
      nameLocation: "middle",
      nameGap: 40,
      axisLabel: {
        formatter(value) {
          return Number(value || 0).toFixed(1);
        },
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { color: "#f0f0f0" } },
    },
    series,
  }, true);
}

function buildSeries(points, expandedKey) {
  const grouped = new Map();

  points.forEach(point => {
    const label = point.label || "UNKNOWN";
    if (!grouped.has(label)) grouped.set(label, []);

    if (
      expandedKey === point.key &&
      Array.isArray(point.article_breakdown) &&
      point.article_breakdown.length > 0
    ) {
      point.article_breakdown.forEach((item, index) => {
        const coord = radialOffset(point, index, point.article_breakdown.length);

        grouped.get(label).push({
          value: coord,
          entity: point.entity,
          label,
          frequency: Number(item.frequency || 0),
          articleName: item.article_name,
          articleId: item.article_id,
          articleCount: 1,
          isContribution: true,
          symbolSize: contributionSizeFromFrequency(Number(item.frequency || 1)),
          itemStyle: { color: getColorForLabel(label), opacity: 0.95 },
        });
      });
      return;
    }

    grouped.get(label).push({
      value: [Number(point.x || 0), Number(point.y || 0)],
      key: point.key,
      entity: point.entity,
      label,
      frequency: Number(point.frequency || 0),
      articleCount: Number(point.article_count || 0),
      isAggregate: true,
      article_breakdown: Array.isArray(point.article_breakdown)
        ? point.article_breakdown
        : [],
      symbolSize: aggregateSizeFromPoint(point),
      itemStyle: { color: getColorForLabel(label), opacity: 0.95 },
    });
  });

  return Array.from(grouped.entries()).map(([label, data]) => ({
    name: label,
    type: "scatter",
    z: 2,
    itemStyle: {
      color: getColorForLabel(label),
    },
    data,
    emphasis: {
      focus: "series",
      scale: true,
    },
    label: {
      show: true,
      position: "top",
      distance: 6,
      color: "#495057",
      fontSize: 10,
      formatter(params) {
        const data = params?.data || {};
        if (data.isContribution) {
          return `${trimLabel(data.articleName || "", 28)} (${Number(data.frequency || 0)})`;
        }
        return `${trimLabel(data.entity || "", 28)} (${Number(data.frequency || 0)})`;
      },
    },
  }));
}

function clearChartHoverState(chart) {
  if (!chart || typeof chart.dispatchAction !== "function") return;
  try {
    chart.dispatchAction({ type: "downplay", seriesIndex: "all" });
    chart.dispatchAction({ type: "hideTip" });
  } catch (_) {}
}

function radialOffset(point, index, total) {
  const radius = 1.3 + Math.min(2.6, total * 0.08);
  const angle = (Math.PI * 2 * index) / Math.max(total, 1);
  return [
    Number(point.x || 0) + Math.cos(angle) * radius,
    Number(point.y || 0) + Math.sin(angle) * radius,
  ];
}

function aggregateSizeFromPoint(point) {
  const frequency = Math.max(1, Number(point.frequency || 1));
  const articleCount = Math.max(1, Number(point.article_count || 1));
  const size =
    13 +
    Math.log2(frequency + 1) * 4.6 +
    Math.log2(articleCount + 1) * 3.8;
  return Math.max(13, Math.min(42, size));
}

function contributionSizeFromFrequency(frequency) {
  const safe = Math.max(1, Number(frequency || 1));
  return Math.max(10, Math.min(22, 9 + Math.log2(safe + 1) * 4));
}

function trimLabel(value, maxLength) {
  const text = String(value || "");
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 1))}…`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
