import { getColorForLabel } from "./categoryColors.js";

let activeWorkspaceRelationKey = null;

const EDGE_COLORS = {
  low: "#7dd3fc",
  medium: "#6366f1",
  high: "#c026d3",
};

export function initWorkspaceRelationsChart(chart, payload = {}, options = {}) {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const allEdges = Array.isArray(payload?.edges) ? payload.edges : [];
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
  const axisRange = computeAxisRange(filtered.nodes);
  const edgeSeriesData = filtered.edges
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
          opacity: edge.muted ? 0.1 : 0.9,
        },
      };
    })
    .filter(Boolean);

  chart.off("click");
  chart.on("click", (params) => {
    const datum = params?.data;
    if (!datum || !datum.isRelationNode) return;
    const hasConnections = edges.some(edge => edge.source === datum.key || edge.target === datum.key);
    if (!hasConnections) return;
    activeWorkspaceRelationKey = activeWorkspaceRelationKey === datum.key ? null : datum.key;
    initWorkspaceRelationsChart(chart, payload, options);
  });

  chart.setOption({
    animation: true,
    animationDuration: 350,
    animationDurationUpdate: 350,
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
          `Tipo dominante: ${escapeHtml(node.label || "UNKNOWN")}`,
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
    graphic: buildRelationLegend(),
    series: [
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
    ],
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
  if (filterMode === "all" || filterMode === "connected") {
    return filterMode;
  }
  return "all";
}

function selectStrongWorkspaceEdges(edges) {
  return Array.isArray(edges) ? edges : [];
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
  return Boolean(tier) || filterMode === "all";
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
  if (filterMode !== "connected") {
    return model;
  }

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
      label,
      frequency: Number(node.frequency || 0),
      articleCount: Number(node.article_count || node.article_count === 0 ? node.article_count : node.articleCount || 0),
      isRelationNode: true,
      muted: Boolean(node.muted),
      selected: Boolean(node.selected),
      symbolSize: sizeFromNode(node),
    });
  });

  return Array.from(grouped.entries()).map(([label, data]) => ({
    name: label,
    type: "scatter",
    z: 2,
    data,
    emphasis: { focus: "none" },
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
    },
  })).map(series => ({
    ...series,
    data: series.data.map(node => ({
      ...node,
      itemStyle: {
        color: getColorForLabel(node.label),
        opacity: node.muted ? 0.22 : (node.selected ? 1 : 0.95),
        borderColor: node.selected ? "#212529" : "#ffffff",
        borderWidth: node.selected ? 2.4 : 1.2,
      },
      label: {
        color: node.muted ? "#9aa1a7" : "#333",
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
    { color: EDGE_COLORS.low, text: "Relacion baja" },
    { color: EDGE_COLORS.medium, text: "Relacion media" },
    { color: EDGE_COLORS.high, text: "Relacion alta" },
  ];

  return [{
    type: "group",
    right: 34,
    bottom: 4,
    silent: true,
    children: labels.flatMap((item, index) => {
      const y = index * 18;
      return [
        {
          type: "circle",
          shape: { cx: 0, cy: y + 10, r: 5 },
          style: {
            fill: item.color,
            stroke: "#ffffff",
            lineWidth: 1,
          },
        },
        {
          type: "text",
          style: {
            x: 12,
            y: y + 4,
            text: item.text,
            fill: "#4b5563",
            font: "12px sans-serif",
          },
        },
      ];
    }),
  }];
}

function computeAxisRange(nodes) {
  if (!Array.isArray(nodes) || !nodes.length) return null;
  const xs = nodes.map(node => Number(node.x || 0)).filter(Number.isFinite);
  const ys = nodes.map(node => Number(node.y || 0)).filter(Number.isFinite);
  if (!xs.length || !ys.length) return null;

  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);

  const xPad = Math.max(1.5, (xMax - xMin) * 0.12);
  const yPad = Math.max(1.5, (yMax - yMin) * 0.12);

  return {
    xMin: xMin - xPad,
    xMax: xMax + xPad,
    yMin: yMin - yPad,
    yMax: yMax + yPad,
  };
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
