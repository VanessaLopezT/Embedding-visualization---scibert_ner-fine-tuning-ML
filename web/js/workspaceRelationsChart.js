import { getColorForLabel } from "./categoryColors.js";

let activeWorkspaceRelationKey = null;

const EDGE_COLORS = {
  low: "#7dd3fc",
  medium: "#6366f1",
  high: "#c026d3",
};

const WORKSPACE_LEGEND_WIDTH = "52%";

export function initWorkspaceRelationsChart(chart, payload = {}, options = {}) {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const allEdges = Array.isArray(payload?.edges) ? payload.edges : [];
  
  // Validar si no hay nodos/entidades
  if (nodes.length === 0) {
    chart.setOption({
      title: {
        text: "No se detectaron entidades",
        subtext: "El workspace no contiene entidades válidas para generar relaciones",
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
      dataZoom: [],
      graphic: []
    }, true);
    return;
  }
  
  // Limpiar título previo cuando hay datos
  chart.setOption({ title: { show: false } }, false);
  
  const nodeMap = new Map(nodes.map(node => [String(node.key || ""), node]));
  const candidateEdges = selectStrongWorkspaceEdges(allEdges);
  const thresholds = computeEdgeThresholds(candidateEdges);
  const filterMode = normalizeFilterMode(options.filterMode);

  const edges = candidateEdges
    .map(edge => ({
      ...edge,
      tier: classifyEdge(Number(edge.score || 0), thresholds),
    }))
    .filter(edge => matchesFilter(edge.tier, filterMode));

  const model = buildSelectionModel(nodes, edges);
  const visibilityFiltered = applyVisibilityFilter(model, filterMode);
  const filtered = applySelection(visibilityFiltered, activeWorkspaceRelationKey);
  const edgeSeriesData = buildEdgeSeriesData(filtered.edges, nodeMap);
  const hasRenderableRelations = filtered.edges.length > 0;

  chart.off("click");
  chart.on("click", (params) => {
    const datum = params?.data;
    if (!datum || !datum.isRelationNode) return;
    const hasConnections = edges.some(edge => edge.source === datum.key || edge.target === datum.key);
    if (!hasConnections) return;
    activeWorkspaceRelationKey = activeWorkspaceRelationKey === datum.key ? null : datum.key;
    initWorkspaceRelationsChart(chart, payload, options);
  });

  chart.off("legendselectchanged");
  chart.on("legendselectchanged", (params) => {
    const selectedLabels = Object.keys(params.selected)
      .filter(label => params.selected[label]);
    const visibleNodeKeys = new Set(
      payload.nodes
        .filter(node => selectedLabels.includes(String(node.label || "")))
        .map(node => String(node.key || ""))
    );
    const filteredEdgeData = buildEdgeSeriesData(filtered.edges, nodeMap, visibleNodeKeys);
    chart.setOption({ series: [{ data: filteredEdgeData }] });
  });

  chart.setOption({
    animation: true,
    animationDuration: 350,
    animationDurationUpdate: 350,
    animationEasing: "cubicOut",
    tooltip: {
      show: true,
      trigger: "item",
      formatter(params) {
        if (params?.seriesType === "lines") {
          const edge = params.data || {};
          const edgeColor = String(edge?.lineStyle?.color || "#495057");
          return [
            `<b style="color:${escapeHtml(edgeColor)};">${escapeHtml(edge.sourceEntity || "")} ↔ ${escapeHtml(edge.targetEntity || "")}</b>`,
            `Afinidad: ${formatScore(edge.score)}`,
            `Coocurrencias en frase: ${Number(edge.sentence_cooccurrence || 0)}`,
            `Solapamiento en chunk: ${formatScore(edge.chunk_jaccard || 0)}`,
            `Similitud de contexto: ${formatScore(edge.profile_similarity || 0)}`,
            `NPMI contextual: ${formatScore(edge.sentence_npmi || 0)}`,
          ].join("<br/>");
        }

        const node = params?.data || {};
        return [
          `<b>${escapeHtml(node.entity || "")}</b>`,
          `Tipo: ${escapeHtml(node.entityLabel || "UNKNOWN")}`,
          `Frecuencia total: ${Number(node.frequency || 0)}`,
          `Articulos del workspace: ${Number(node.articleCount || 0)}`,
        ].join("<br/>");
      },
    },
    toolbox: {
      feature: {
        dataZoom: {},
        restore: {
          onclick: () => { activeWorkspaceRelationKey = null; },
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
    xAxis: hasRenderableRelations ? {
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
    } : {
      type: "value",
      show: false,
    },
    yAxis: hasRenderableRelations ? {
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
    } : {
      type: "value",
      show: false,
    },
    graphic: hasRenderableRelations ? buildRelationLegend() : buildNoRelationsGraphic(filterMode),
    series: hasRenderableRelations ? [
      {
        type: "lines",
        coordinateSystem: "cartesian2d",
        polyline: false,
        silent: false,
        z: 1,
        emphasis: {
          focus: "none",
          lineStyle: {
            width: 3.2,
            opacity: 1,
          },
        },
        data: edgeSeriesData,
      },
      ...buildNodeSeries(filtered.nodes),
    ] : [],
  }, true);

  if (typeof options.onRenderSummary === "function") {
    queueMicrotask(() => {
      options.onRenderSummary({
        visibleNodeCount: filtered.nodes.length,
        visibleEdgeCount: filtered.edges.length,
      });
    });
  }
}

export function resetWorkspaceRelationsSelection() {
  activeWorkspaceRelationKey = null;
}

function normalizeFilterMode(filterMode) {
  if (["all", "connected", "low", "medium", "high"].includes(filterMode)) {
    return filterMode;
  }
  return "all";
}

function selectStrongWorkspaceEdges(edges) {
  return Array.isArray(edges) ? edges : [];
}

function buildEdgeSeriesData(edges, nodeMap, visibleNodeKeys = null) {
  return Array.isArray(edges)
    ? edges
        .filter(edge => {
          if (!visibleNodeKeys) return true;
          return (
            visibleNodeKeys.has(String(edge.source || "")) &&
            visibleNodeKeys.has(String(edge.target || ""))
          );
        })
        .map(edge => {
          const source = nodeMap.get(String(edge.source || ""));
          const target = nodeMap.get(String(edge.target || ""));
          if (!source || !target) return null;
          return {
            ...edge,
            sourceEntity: edge.source_entity,
            targetEntity: edge.target_entity,
            coords: [
              [Number(source.x || 0), Number(source.y || 0)],
              [Number(target.x || 0), Number(target.y || 0)],
            ],
            lineStyle: {
              color: edge.muted ? "#d6dde3" : EDGE_COLORS[edge.tier],
              width: 2.4,
              opacity: edge.muted ? 0.1 : 1,
              curveness: 0.08,
            },
          };
        })
        .filter(Boolean)
    : [];
}

function computeEdgeThresholds(edges) {
  const scores = edges
    .map(edge => Number(edge.score || 0))
    .filter(score => Number.isFinite(score))
    .sort((left, right) => left - right);

  if (!scores.length) {
    return { low: 0.33, high: 0.66 };
  }

  return {
    low: percentile(scores, 0.33),
    high: percentile(scores, 0.66),
  };
}

function percentile(sortedValues, p) {
  if (!sortedValues.length) return 0;
  const index = (sortedValues.length - 1) * p;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sortedValues[lower];
  const weight = index - lower;
  return sortedValues[lower] * (1 - weight) + sortedValues[upper] * weight;
}

function classifyEdge(score, thresholds) {
  if (score >= thresholds.high) return "high";
  if (score >= thresholds.low) return "medium";
  return "low";
}

function matchesFilter(tier, filterMode) {
  if (filterMode === "all" || filterMode === "connected") return Boolean(tier);
  return tier === filterMode;
}

function buildSelectionModel(nodes, edges) {
  const degreeMap = new Map();
  edges.forEach(edge => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1);
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1);
  });

  return {
    nodes: nodes.map(node => ({
      ...node,
      degree: degreeMap.get(node.key) || 0,
    })),
    edges,
  };
}

function applyVisibilityFilter(model, filterMode) {
  // Para "all", mostrar todos los nodos (incluyendo aislados)
  if (filterMode === "all") {
    return model;
  }

  // Para cualquier otro filtro (connected, low, medium, high),
  // solo mostrar nodos que tienen al menos una arista
  const connectedKeys = new Set();
  model.edges.forEach(edge => {
    connectedKeys.add(edge.source);
    connectedKeys.add(edge.target);
  });

  return {
    nodes: model.nodes.filter(node => connectedKeys.has(node.key)),
    edges: model.edges,
  };
}

function applySelection(model, selectedKey) {
  if (!selectedKey) return model;

  const connectedEdges = model.edges.filter(edge => edge.source === selectedKey || edge.target === selectedKey);
  const connectedKeys = new Set([selectedKey]);
  connectedEdges.forEach(edge => {
    connectedKeys.add(edge.source);
    connectedKeys.add(edge.target);
  });

  return {
    nodes: model.nodes
      .filter(node => connectedKeys.has(node.key))
      .map(node => ({
      ...node,
      muted: false,
      selected: node.key === selectedKey,
    })),
    edges: connectedEdges.map(edge => ({
      ...edge,
      muted: false,
    })),
  };
}

function buildNodeSeries(nodes) {
  const grouped = new Map();
  nodes.forEach(node => {
    const label = node.label || "UNKNOWN";
    if (!grouped.has(label)) grouped.set(label, []);
    grouped.get(label).push({
      key: node.key,
      value: [Number(node.x || 0), Number(node.y || 0)],
      entity: node.entity,
      entityLabel: label,
      frequency: Number(node.frequency || 0),
      articleCount: Number(node.article_count || node.article_count === 0 ? node.article_count : node.articleCount || 0),
      isRelationNode: true,
      muted: Boolean(node.muted),
      selected: Boolean(node.selected),
      symbolSize: sizeFromNode(node),
    });
  });

  const selectionActive = Boolean(activeWorkspaceRelationKey);

  return Array.from(grouped.entries()).map(([label, data]) => ({
    name: label,
    type: "scatter",
    z: 2,
    data,
    emphasis: {
      focus: "none",
      scale: true,
    },
    label: {
      show: true,
      position: "top",
      distance: 6,
      color: "#333",
      fontSize: 10,
      formatter(params) {
        return String(params?.data?.entity || "");
      },
    },
    itemStyle: {
      color: getColorForLabel(label),
      opacity: 1,
    },
  })).map(series => ({
    ...series,
    data: series.data.map(node => ({
      ...node,
      itemStyle: {
        color: getColorForLabel(node.entityLabel),
        opacity: selectionActive ? 1 : (node.muted ? 0.22 : 1),
        borderColor: node.selected ? "#212529" : "#ffffff",
        borderWidth: node.selected ? 2.4 : 1.2,
      },
      label: {
        color: selectionActive ? "#333" : (node.muted ? "#9aa1a7" : "#333"),
        fontWeight: node.selected ? 600 : 400,
      },
    })),
  }));
}

function sizeFromNode(node) {
  const frequency = Math.max(1, Number(node.frequency || 1));
  const articleCount = Math.max(1, Number(node.article_count || node.articleCount || 1));
  const baseSize = 13 + Math.log2(frequency + 1) * 4.6 + Math.log2(articleCount + 1) * 3.8;
  const boosted = node.selected ? baseSize + 5 : baseSize;
  return Math.max(13, Math.min(42, boosted));
}

function buildRelationLegend() {
  const labels = [
    { color: EDGE_COLORS.low, text: "Baja" },
    { color: EDGE_COLORS.medium, text: "Media" },
    { color: EDGE_COLORS.high, text: "Alta" },
  ];
  const itemWidth = 68;

  return [{
    type: "group",
    right: 14,
    bottom: 12,
    silent: true,
    children: [
      {
        type: "text",
        style: {
          x: 0,
          y: 1,
          text: "Relación:",
          fill: "#6b7280",
          font: "11px sans-serif",
        },
      },
      ...labels.flatMap((item, index) => {
        const x = 58 + index * itemWidth;
        return [
          {
            type: "line",
            shape: { x1: x, y1: 8, x2: x + 14, y2: 8 },
            style: { stroke: item.color, lineWidth: 3, lineCap: "round" },
          },
          {
            type: "text",
            style: {
              x: x + 20,
              y: 1,
              text: item.text,
              fill: "#4b5563",
              font: "11px sans-serif",
            },
          },
        ];
      }),
    ],
  }];
}

function buildNoRelationsGraphic(filterMode) {
  const message = filterMode === "connected"
    ? "No hay relaciones para mostrar con ese filtro."
    : filterMode === "low"
      ? "No hay relaciones bajas."
      : filterMode === "medium"
        ? "No hay relaciones medias."
        : filterMode === "high"
          ? "No hay relaciones altas."
          : "No hay relaciones para mostrar.";

  return [{
    type: "group",
    left: "center",
    top: "middle",
    silent: true,
    children: [
          {
        type: "text",
        style: {
          x: -150,
          y: 16,
          text: message,
          fill: "#6b7280",
          font: "12px sans-serif",
        },
      },
    ],
  }];
}

function formatScore(value) {
  return Number(value || 0).toFixed(3);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
