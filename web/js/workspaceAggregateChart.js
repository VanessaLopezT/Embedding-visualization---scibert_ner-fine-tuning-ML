import { getColorForLabel } from "./categoryColors.js";

let expandedEntityKey = null;
let workspaceAxisRange = null;

export function initWorkspaceAggregateChart(chart, payload = {}) {
  const points = Array.isArray(payload?.points) ? payload.points : [];
  renderWorkspaceAggregate(chart, points);

  chart.off("click");
  chart.on("click", (params) => {
    const data = params?.data;
    if (!data) return;

    if (data.isAggregate) {
      if (Number(data.articleCount || 0) <= 1) return;
      expandedEntityKey = expandedEntityKey === data.key ? null : data.key;
      renderWorkspaceAggregate(chart, points);
      return;
    }

    if (data.isContribution) {
      expandedEntityKey = null;
      renderWorkspaceAggregate(chart, points);
    }
  });
}

export function resetWorkspaceAggregateExpansion() {
  expandedEntityKey = null;
  workspaceAxisRange = null;
}

function renderWorkspaceAggregate(chart, points) {
  const axisRange = workspaceAxisRange || getCurrentAxisRange(chart);
  const series = buildSeries(points, expandedEntityKey);

  chart.setOption({
    animation: true,
    animationDuration: 0,
    animationDurationUpdate: 0,
    tooltip: {
      show: true,
      formatter(params) {
        const data = params?.data || {};
        if (data.isContribution) {
          return [
            `<b>${escapeHtml(data.entity || "")}</b>`,
            `Articulo: ${escapeHtml(data.articleName || "")}`,
            `Frecuencia en articulo: ${Number(data.frequency || 0)}`,
            `Tipo dominante: ${escapeHtml(data.label || "UNKNOWN")}`,
          ].join("<br/>");
        }

        return [
          `<b>${escapeHtml(data.entity || "")}</b>`,
          `Tipo dominante: ${escapeHtml(data.label || "UNKNOWN")}`,
          `Frecuencia total: ${Number(data.frequency || 0)}`,
          `Articulos del workspace: ${Number(data.articleCount || 0)}`,
        ].join("<br/>");
      },
    },
    toolbox: {
      feature: { dataZoom: {}, restore: { onclick: () => { expandedEntityKey = null; } }, saveAsImage: {} },
      right: 20,
      top: 20,
    },
    legend: {
      top: 22,
      left: "center",
      orient: "horizontal",
      textStyle: {
        fontSize: 13,
        color: "#333",
        fontWeight: 500,
      },
      backgroundColor: "rgba(255, 255, 255, 0.8)",
      borderColor: "#e0e0e0",
      borderWidth: 1,
      borderRadius: 4,
      padding: 8,
      itemGap: 25,
      itemWidth: 12,
      itemHeight: 12,
    },
    grid: {
      left: 60,
      right: 30,
      bottom: 40,
      top: 82,
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
      ...(axisRange ? { min: axisRange.xMin, max: axisRange.xMax } : {}),
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
      ...(axisRange ? { min: axisRange.yMin, max: axisRange.yMax } : {}),
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

    if (expandedKey === point.key && Array.isArray(point.article_breakdown) && point.article_breakdown.length > 1) {
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
          labelCfg: {
            show: true,
            formatter: `${trimLabel(item.article_name, 28)} (${Number(item.frequency || 0)})`,
          },
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
      symbolSize: aggregateSizeFromPoint(point),
      itemStyle: { color: getColorForLabel(label), opacity: 0.95 },
      labelCfg: {
        show: true,
        formatter: `${trimLabel(point.entity, 28)} (${Number(point.frequency || 0)})`,
      },
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
    emphasis: { focus: "series" },
    label: {
      show: true,
      position: "top",
      distance: 6,
      color: "#495057",
      fontSize: 10,
      formatter(params) {
        return params?.data?.labelCfg?.formatter || "";
      },
    },
  }));
}

function radialOffset(point, index, total) {
  const radius = 1.3 + Math.min(2.6, total * 0.08);
  const angle = (Math.PI * 2 * index) / Math.max(total, 1);
  return [
    Number(point.x || 0) + (Math.cos(angle) * radius),
    Number(point.y || 0) + (Math.sin(angle) * radius),
  ];
}

function aggregateSizeFromPoint(point) {
  const frequency = Math.max(1, Number(point.frequency || 1));
  const articleCount = Math.max(1, Number(point.article_count || 1));
  const size = 14 + Math.log2(frequency + 1) * 5 + Math.log2(articleCount + 1) * 4;
  return Math.max(14, Math.min(44, size));
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

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
