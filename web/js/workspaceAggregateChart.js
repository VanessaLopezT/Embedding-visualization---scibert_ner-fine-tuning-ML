import { getColorForLabel, ambosOriginFillColor, ambosSeriesLegendFill } from "./categoryColors.js?v=20260501h";
import {
  ENTITY_POINT_LABEL_COLOR,
  WORKSPACE_AXIS_TICK_COLOR,
  WORKSPACE_CATEGORY_LEGEND_LEFT,
  WORKSPACE_CATEGORY_LEGEND_WIDTH,
  workspaceAggregateSymbolSize,
  workspaceChartDataZoomInside,
  workspaceScatterAxesFromExtent,
} from "./chartAxisUtils.js?v=20260502rel_axes_fix";

let expandedEntityKey = null;

export function initWorkspaceAggregateChart(chart, payload = {}, options = {}) {
  const points = Array.isArray(payload?.points) ? payload.points : [];
  const combinedView = Boolean(options.combinedView);

  renderWorkspaceAggregate(chart, points, { combinedView });
  requestAnimationFrame(() => {
    chart.resize();
    requestAnimationFrame(() => chart.resize());
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
          try {
            chart.dispatchAction({ type: "downplay", seriesIndex: "all" });
          } catch (_) {}
          renderWorkspaceAggregate(chart, points, { combinedView });
          clearChartHoverState(chart);
        }
        return;
      }

      try {
        chart.dispatchAction({ type: "downplay", seriesIndex: "all" });
      } catch (_) {}
      expandedEntityKey = expandedEntityKey === data.key ? null : data.key;
      renderWorkspaceAggregate(chart, points, { combinedView });
      clearChartHoverState(chart);
      return;
    }

    if (data.isContribution) {
      expandedEntityKey = null;

      try {
        chart.dispatchAction({ type: "downplay", seriesIndex: "all" });
      } catch (_) {}

      renderWorkspaceAggregate(chart, points, { combinedView });
      clearChartHoverState(chart);
    }
  });

  chart.on("mouseout", () => {
    clearChartHoverState(chart);
  });
}

export function resetWorkspaceAggregateExpansion() {
  expandedEntityKey = null;
}

function extentFromWorkspaceSeries(series) {
  const xs = [];
  const ys = [];
  for (const s of series || []) {
    for (const d of s.data || []) {
      const v = d?.value;
      if (!Array.isArray(v) || v.length < 2) continue;
      const x = Number(v[0]);
      const y = Number(v[1]);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        xs.push(x);
        ys.push(y);
      }
    }
  }
  if (!xs.length) return null;
  return {
    xMin: Math.min(...xs),
    xMax: Math.max(...xs),
    yMin: Math.min(...ys),
    yMax: Math.max(...ys),
  };
}

function workspaceAggregateAxesFromSeries(series, combinedView) {
  return workspaceScatterAxesFromExtent(
    extentFromWorkspaceSeries(series),
    0.07,
    6,
    combinedView ? "square" : false,
  );
}

function renderWorkspaceAggregate(chart, points, viewOpts = {}) {
  const combinedView = Boolean(viewOpts.combinedView);
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
  
  const collapsedSeries = buildSeries(points, null, { combinedView });
  const series = buildSeries(points, expandedEntityKey, { combinedView });
  const zoomState = readWorkspaceAggregateDataZoomState(chart);
  // Misma idea que frecuencia por artículo: el marco de ejes no debe recalcularse
  // con los puntos radiales del desglose; si no, el resto de agregados "saltan".
  const axesModel = workspaceAggregateAxesFromSeries(collapsedSeries, combinedView);
  const fallbackAxis = (name, nameGap) => ({
    type: "value",
    scale: true,
    name,
    nameLocation: "middle",
    nameGap,
    nameTextStyle: {
      color: ENTITY_POINT_LABEL_COLOR,
      fontSize: 12,
      fontWeight: 600,
    },
    axisLabel: {
      formatter(value) {
        return Number(value || 0).toFixed(2);
      },
      color: WORKSPACE_AXIS_TICK_COLOR,
      fontSize: 11,
    },
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { show: true, lineStyle: { color: "#f0f0f0" } },
  });

  // Animación alineada a tsneChart (artículo): zoom/coordenadas fluidas; expandir/colapsar
  // entidad también anima (~350ms) igual que vista individual.
  chart.setOption({
    animation: true,
    animationDuration: 350,
    animationDurationUpdate: 0,
    animationEasing: "cubicOut",
    animationEasingUpdate: "linear",
    tooltip: {
      show: true,
      formatter(params) {
        const data = params?.data || {};
        const originLine = (() => {
          if (!combinedView) return "";
          const o = String(data.dominant_origin || data.dominantOrigin || "").toLowerCase();
          if (!o) return "";
          const lab = o === "tech" ? "TechBERT" : o === "cmt" ? "PatVetBERT" : "Coincidencia ambos modelos";
          return `<br/>Origen (mayoritario): ${lab}`;
        })();

        if (data.isContribution) {
          return [
            `<b>${escapeHtml(data.entity || "")}</b>`,
            `Articulo: ${escapeHtml(data.articleName || "")}`,
            `Frecuencia en artículo: ${Number(data.frequency || 0)}`,
            `Tipo: ${escapeHtml(data.label || "UNKNOWN")}`,
            originLine,
          ].join("<br/>");
        }

        return [
          `<b>${escapeHtml(data.entity || "")}</b>`,
          `Tipo: ${escapeHtml(data.label || "UNKNOWN")}`,
          `Frecuencia total: ${Number(data.frequency || 0)}`,
          `Articulos del workspace: ${Number(data.articleCount || 0)}`,
          originLine,
        ].join("<br/>");
      },
    },
    toolbox: {
      feature: {
        dataZoom: {},
        restore: {
          onclick: () => {
            expandedEntityKey = null;
            renderWorkspaceAggregate(chart, points, viewOpts);
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
      left: WORKSPACE_CATEGORY_LEGEND_LEFT,
      width: WORKSPACE_CATEGORY_LEGEND_WIDTH,
      orient: "horizontal",
      textStyle: {
        fontSize: 12,
        color: ENTITY_POINT_LABEL_COLOR,
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
    dataZoom: workspaceChartDataZoomInside().map((z) => {
      const isX = Array.isArray(z?.xAxisIndex) && z.xAxisIndex.includes(0);
      const isY = Array.isArray(z?.yAxisIndex) && z.yAxisIndex.includes(0);
      if (isX) {
        return { ...z, start: zoomState?.x?.start ?? z.start, end: zoomState?.x?.end ?? z.end };
      }
      if (isY) {
        return { ...z, start: zoomState?.y?.start ?? z.start, end: zoomState?.y?.end ?? z.end };
      }
      return z;
    }),
    xAxis: axesModel?.xAxis ?? fallbackAxis("Dimension 1", 30),
    yAxis: axesModel?.yAxis ?? fallbackAxis("Dimension 2", 40),
    series,
  }, true);
  // Limpia estados de énfasis pegados tras re-render (evita nodos "invisibles"
  // que reaparecen solo al pasar el mouse).
  requestAnimationFrame(() => clearChartHoverState(chart));
}

function readWorkspaceAggregateDataZoomState(chart) {
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

function buildSeries(points, expandedKey, opts = {}) {
  const combinedView = Boolean(opts.combinedView);
  const grouped = new Map();

  points.forEach(point => {
    const label = point.label || "UNKNOWN";
    if (!grouped.has(label)) grouped.set(label, []);
    const domOrigin = String(point.dominant_origin || point.dominantOrigin || "joint").toLowerCase() || "joint";

    if (
      expandedKey === point.key &&
      Array.isArray(point.article_breakdown) &&
      point.article_breakdown.length > 0
    ) {
      point.article_breakdown.forEach((item, index) => {
        const coord = radialOffset(point, index, point.article_breakdown.length);
        const fill = combinedView ? ambosOriginFillColor(label, domOrigin) : getColorForLabel(label);

        grouped.get(label).push({
          value: coord,
          entity: point.entity,
          label,
          dominant_origin: domOrigin,
          frequency: Number(item.frequency || 0),
          articleName: item.article_name,
          articleId: item.article_id,
          articleCount: 1,
          isContribution: true,
          symbolSize: contributionSizeFromFrequency(Number(item.frequency || 1)),
          itemStyle: {
            color: fill,
            opacity: 0.95,
            borderColor: "#ffffff",
            borderWidth: 1,
          },
          emphasis: {
            focus: "series",
            scale: true,
          },
        });
      });
      return;
    }

    const fillAgg = combinedView ? ambosOriginFillColor(label, domOrigin) : getColorForLabel(label);
    grouped.get(label).push({
      value: [Number(point.x || 0), Number(point.y || 0)],
      key: point.key,
      entity: point.entity,
      label,
      dominant_origin: domOrigin,
      frequency: Number(point.frequency || 0),
      articleCount: Number(point.article_count || 0),
      isAggregate: true,
      article_breakdown: Array.isArray(point.article_breakdown)
        ? point.article_breakdown
        : [],
      symbolSize: aggregateSizeFromPoint(point),
      itemStyle: {
        color: fillAgg,
        opacity: 0.95,
        borderColor: "#ffffff",
        borderWidth: 1,
      },
      emphasis: {
        focus: "series",
        scale: true,
      },
    });
  });

  return Array.from(grouped.entries()).map(([label, data]) => ({
    name: label,
    type: "scatter",
    z: 2,
    symbol: "circle",
    symbolSize: (_v, params) => params?.data?.symbolSize ?? 16,
    itemStyle: combinedView
      ? {
          color: ambosSeriesLegendFill(
            label,
            data.map((d) => d.dominant_origin || d.dominantOrigin || "joint"),
          ),
          opacity: 1,
          borderColor: "#ffffff",
          borderWidth: 1,
        }
      : {
          color: getColorForLabel(label),
          borderColor: "#ffffff",
          borderWidth: 1,
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
      color: ENTITY_POINT_LABEL_COLOR,
      fontSize: 10,
      fontWeight: 500,
      formatter(params) {
        const d = params?.data || {};
        if (d.isContribution) {
          return `${trimLabel(d.articleName || "", 28)} (${Number(d.frequency || 0)})`;
        }
        return `${trimLabel(d.entity || "", 28)} (${Number(d.frequency || 0)})`;
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
  return workspaceAggregateSymbolSize(point);
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
