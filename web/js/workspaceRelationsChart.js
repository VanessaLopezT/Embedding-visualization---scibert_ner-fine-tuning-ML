import { getColorForLabel, ambosOriginFillColor, ambosSeriesLegendFill } from "./categoryColors.js?v=20260501h";
import {
  ENTITY_POINT_LABEL_COLOR,
  WORKSPACE_CATEGORY_LEGEND_LEFT,
  WORKSPACE_CATEGORY_LEGEND_WIDTH,
  extentFromScatterNodes,
  normalizeEntityAggregateKey,
  workspaceAggregateSymbolSize,
  workspaceScatterAxesFromExtent,
  workspaceChartDataZoomInside,
} from "./chartAxisUtils.js?v=20260607_article_xy_overlay";
import { relationLineCurveness } from "./relationLineCurveness.js?v=20260601c";

let activeWorkspaceRelationKey = null;

const EDGE_COLORS = {
  low: "#7dd3fc",
  medium: "#6366f1",
  high: "#c026d3",
};

/** Igual que `workspaceAggregateChart.js` para misma altura útil del gráfico. */
const WORKSPACE_LEGEND_TOP_PX = 4;
const WORKSPACE_GRID_TOP_PX = 78;

/** Alineado con `tsneChartRelations.js` / `tsneChart.js` (modo artículo individual). */
const ARTICLE_REL_LEGEND_TOP_PX = 76;
const ARTICLE_REL_GRID_TOP_PX = 154;
const ARTICLE_LEGEND_WIDTH_TECH = "auto";
const ARTICLE_LEGEND_WIDTH_CMT = "56%";
const ARTICLE_LEGEND_WIDTH_WRAP = "52%";

function buildArticleRelationsLegendConfig(labels = [], opts = {}) {
  const combinedView = Boolean(opts.combinedView);
  const uniqueLabels = Array.from(new Set(labels.map((label) => String(label || "").trim()).filter(Boolean)));
  const usesCmtLabels = labels.some((label) => /\/| and |oncology|treatment/i.test(String(label || "")));
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

/** Igual que `tsneChartRelations.nodeSizeFromFrequency` (bolitas más pequeñas que workspace agregado). */
function articleRelationSymbolSize(frequency, referenceMax) {
  const freq = Number(frequency);
  const refMax = Number(referenceMax);
  if (!Number.isFinite(freq) || freq <= 1) return 16;
  if (!Number.isFinite(refMax) || refMax <= 1) return 16;

  const minRepeated = 2;
  const minSize = 20;
  const maxSize = 60;
  const alpha = 0.65;

  if (refMax <= minRepeated) return minSize;

  const logMin = Math.log(minRepeated);
  const logMax = Math.log(refMax);
  const logF = Math.log(Math.max(freq, minRepeated));
  const t = (logF - logMin) / Math.max(logMax - logMin, 1e-9);
  return minSize + (maxSize - minSize) * Math.pow(Math.max(0, Math.min(1, t)), alpha);
}

function emptyWorkspaceRelationsOption(subtext) {
  return {
    title: {
      text: "No se detectaron entidades",
      subtext,
      left: "center",
      top: "center",
      textStyle: {
        fontSize: 16,
        color: "#666",
        fontWeight: "normal",
      },
      subtextStyle: {
        fontSize: 12,
        color: "#999",
      },
    },
    series: [],
    legend: { show: false },
    xAxis: { show: false },
    yAxis: { show: false },
    toolbox: { show: false },
    dataZoom: [],
    graphic: [],
  };
}

function notifyWorkspaceRelationsSummary(options, counts) {
  if (typeof options.onRenderSummary !== "function") return;
  queueMicrotask(() => {
    options.onRenderSummary(counts);
  });
}

/**
 * Artículo individual: el API usa proyección agregada distinta al JSON t-SNE del panel.
 * Se sobrescribe x/y con el centroide por entidad sobre las mismas filas que Original/Frecuencia.
 */
function overlayArticleNodePositionsFromClientTsne(nodes, tsneRows) {
  if (!Array.isArray(nodes) || !nodes.length || !Array.isArray(tsneRows) || !tsneRows.length) {
    return nodes;
  }
  const buckets = new Map();
  for (const p of tsneRows) {
    const raw = String(p?.entity ?? "").trim();
    if (!raw) continue;
    const k = normalizeEntityAggregateKey(raw);
    if (!buckets.has(k)) buckets.set(k, { sx: 0, sy: 0, n: 0 });
    const b = buckets.get(k);
    b.sx += Number(p?.x ?? 0);
    b.sy += Number(p?.y ?? 0);
    b.n += 1;
  }
  const centroidByKey = new Map();
  for (const [k, b] of buckets) {
    if (b.n > 0) centroidByKey.set(k, { x: b.sx / b.n, y: b.sy / b.n });
  }
  return nodes.map((node) => {
    const sid = String(node?.key ?? "");
    let pos = centroidByKey.get(sid);
    if (!pos && node?.entity != null) {
      pos = centroidByKey.get(normalizeEntityAggregateKey(String(node.entity)));
    }
    if (!pos) return { ...node };
    return { ...node, x: pos.x, y: pos.y };
  });
}

export function initWorkspaceRelationsChart(chart, payload = {}, options = {}) {
  const articleLayout = Boolean(options.articleLayout);
  let nodes = Array.isArray(payload?.nodes) ? [...payload.nodes] : [];
  if (
    articleLayout &&
    Array.isArray(options.clientTsnePoints) &&
    options.clientTsnePoints.length
  ) {
    nodes = overlayArticleNodePositionsFromClientTsne(nodes, options.clientTsnePoints);
  }
  const allEdges = Array.isArray(payload?.edges) ? payload.edges : [];
  const combinedView = Boolean(
    options.combinedView ?? (String(payload?.model || "").toLowerCase() === "ambos"),
  );

  chart.off("click");
  chart.off("legendselectchanged");

  // Validar si no hay nodos/entidades en el payload
  if (nodes.length === 0) {
    chart.setOption(emptyWorkspaceRelationsOption(
      "El workspace no contiene entidades válidas para generar relaciones",
    ), true);
    notifyWorkspaceRelationsSummary(options, { visibleNodeCount: 0, visibleEdgeCount: 0 });
    return;
  }

  // Limpiar título previo cuando hay datos
  chart.setOption({ title: { show: false } }, false);

  const nodeKeySet = new Set(nodes.map((node) => String(node.key || "")));
  if (activeWorkspaceRelationKey && !nodeKeySet.has(String(activeWorkspaceRelationKey))) {
    activeWorkspaceRelationKey = null;
  }

  const nodeMap = new Map(nodes.map(node => [String(node.key || ""), node]));
  const candidateEdges = selectStrongWorkspaceEdges(allEdges);
  const serverFloorRaw = Number(payload?.score_threshold_used);
  const serverFloor = Number.isFinite(serverFloorRaw)
    ? serverFloorRaw
    : 0.24;
  const optMin = Number(options.minScore);
  const minScore = Number.isFinite(optMin)
    ? Math.min(0.995, Math.max(serverFloor, optMin))
    : serverFloor;
  const scorePassEdges = candidateEdges.filter(
    (e) => Number(e.score ?? 0) >= minScore - 1e-9,
  );
  const thresholds = computeEdgeThresholds(scorePassEdges);
  const filterMode = normalizeFilterMode(options.filterMode);

  const edges = scorePassEdges
    .map((edge) => ({
      ...edge,
      tier: classifyEdge(Number(edge.score || 0), thresholds),
    }))
    .filter((edge) => matchesFilter(edge.tier, filterMode));

  const model = buildSelectionModel(nodes, edges);
  const visibilityFiltered = applyVisibilityFilter(model, filterMode);
  let filtered = applySelection(visibilityFiltered, activeWorkspaceRelationKey);
  if (
    activeWorkspaceRelationKey &&
    filtered.edges.length === 0 &&
    visibilityFiltered.edges.length > 0
  ) {
    activeWorkspaceRelationKey = null;
    filtered = applySelection(visibilityFiltered, null);
  }

  if (!filtered.nodes.length) {
    chart.setOption(emptyWorkspaceRelationsOption(
      "Con el filtro actual no quedan entidades visibles. Prueba con «Todas las entidades» u otro nivel de relación.",
    ), true);
    notifyWorkspaceRelationsSummary(options, { visibleNodeCount: 0, visibleEdgeCount: 0 });
    return;
  }

  const edgeSeriesData = buildEdgeSeriesData(filtered.edges, nodeMap);
  const hasRenderableRelations = filtered.edges.length > 0;
  /** Misma caja que vista General/agregado: **todos** los nodos del payload, no solo los que pasan filtro. */
  const extentNodes = extentFromScatterNodes(nodes);
  let axesModel = null;
  if (hasRenderableRelations && extentNodes) {
    axesModel = workspaceScatterAxesFromExtent(
      extentNodes,
      0.07,
      6,
      combinedView ? "square" : false,
    );
  }

  const articleLegendConfig = articleLayout
    ? buildArticleRelationsLegendConfig(
        filtered.nodes.map((n) => n.label || "UNKNOWN"),
        { combinedView },
      )
    : null;

  const scatterSeries = buildNodeSeries(filtered.nodes, { combinedView, articleLayout });
  const lineSeries = hasRenderableRelations
    ? [
        {
          id: "workspace-relations-edges",
          type: "lines",
          coordinateSystem: "cartesian2d",
          clip: true,
          polyline: false,
          silent: false,
          z: 1,
          effect: { show: false },
          showInLegend: false,
          showLegendSymbol: false,
          legendHoverLink: false,
          lineStyle: {
            width: 2.4,
            opacity: 1,
            color: "#7f8c8d",
            curveness: 0.1,
          },
          data: edgeSeriesData,
          tooltip: { show: true },
        },
      ]
    : [];
  /** Como tsneChartRelations.js: si no hay aristas, no puntos ni ejes — solo mensaje centrado. */
  const series = hasRenderableRelations ? [...lineSeries, ...scatterSeries] : [];
  const showAxes = hasRenderableRelations;

  /** Misma familia global que tsneChartRelations.js (articulo individual). */
  const animationGlobals = {
    animation: true,
    animationDuration: 350,
    animationDurationUpdate: 350,
    animationEasing: "cubicOut",
    animationEasingUpdate: "cubicOut",
  };

  chart.setOption({
    ...animationGlobals,
    tooltip: {
      show: true,
      formatter(params) {
        if (params?.seriesType === "lines") {
          const edge = params.data || {};
          const edgeColor = String(edge?.lineStyle?.color || "#495057");
          const semanticNote =
            edge.semantic_embedding_bridge || edge.semantic_embedding_bridge === true
              ? `<br/><span style="color:#555;font-size:11px;">Puente semántico (embeddings Tech+PatVet, coseno ${formatScore(edge.embedding_cosine ?? edge.profile_similarity)} )</span>`
              : "";
          return [
            `<b style="color:${escapeHtml(edgeColor)};">${escapeHtml(edge.sourceEntity || "")} ↔ ${escapeHtml(edge.targetEntity || "")}</b>`,
            `Afinidad: ${formatScore(edge.score)}`,
            `Coocurrencias en frase: ${Number(edge.sentence_cooccurrence || 0)}`,
            `Solapamiento en chunk: ${formatScore(edge.chunk_jaccard || 0)}`,
            `Similitud de contexto: ${formatScore(edge.profile_similarity || 0)}`,
            `NPMI contextual: ${formatScore(edge.sentence_npmi || 0)}`,
            semanticNote,
          ].join("<br/>");
        }

        const node = params?.data || {};
        const lines = [
          `<b>${escapeHtml(node.entity || "")}</b>`,
          `Tipo: ${escapeHtml(node.entityType || "UNKNOWN")}`,
          `Frecuencia total: ${Number(node.frequency || 0)}`,
        ];
        if (!articleLayout) {
          lines.push(`Articulos del workspace: ${Number(node.articleCount || 0)}`);
        }
        const origin = node.dominantOrigin ?? node.dominant_origin;
        if (combinedView && origin) {
          const o = String(origin).toLowerCase();
          const lab = o === "tech" ? "TechBERT" : o === "cmt" ? "PatVetBERT" : "Coincidencia ambos modelos";
          lines.push(`Origen (mayoritario): ${lab}`);
        }
        return lines.join("<br/>");
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
    legend: articleLayout && articleLegendConfig
      ? {
          top: ARTICLE_REL_LEGEND_TOP_PX,
          left: "center",
          width: articleLegendConfig.width,
          orient: "horizontal",
          textStyle: {
            fontSize: 12,
            color: ENTITY_POINT_LABEL_COLOR,
            fontWeight: 500,
          },
          backgroundColor: articleLegendConfig.backgroundColor,
          borderColor: articleLegendConfig.borderColor,
          borderWidth: articleLegendConfig.borderWidth,
          borderRadius: articleLegendConfig.borderRadius,
          padding: articleLegendConfig.padding,
          itemGap: 12,
          itemWidth: 11,
          itemHeight: 11,
        }
      : {
          type: "plain",
          top: WORKSPACE_LEGEND_TOP_PX,
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
      top: articleLayout ? ARTICLE_REL_GRID_TOP_PX : WORKSPACE_GRID_TOP_PX,
      containLabel: true,
    },
    backgroundColor: "#fafafa",
    dataZoom: hasRenderableRelations ? workspaceChartDataZoomInside() : [],
    xAxis: showAxes
      ? {
          ...(axesModel?.xAxis ?? {
            type: "value",
            scale: true,
            name: "Dimension 1",
            nameLocation: "middle",
            nameGap: 30,
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { show: true, lineStyle: { color: "#f0f0f0" } },
          }),
        }
      : {
          type: "value",
          show: false,
        },
    yAxis: showAxes
      ? {
          ...(axesModel?.yAxis ?? {
            type: "value",
            scale: true,
            name: "Dimension 2",
            nameLocation: "middle",
            nameGap: 40,
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { show: true, lineStyle: { color: "#f0f0f0" } },
          }),
        }
      : {
          type: "value",
          show: false,
        },
    graphic: hasRenderableRelations ? buildRelationLegend() : buildNoRelationsGraphic(filterMode),
    series,
  }, { notMerge: true, lazyUpdate: false });

  notifyWorkspaceRelationsSummary(options, {
    visibleNodeCount: filtered.nodes.length,
    visibleEdgeCount: filtered.edges.length,
  });

  // Tras aplicar opción completa (igual orden que tsneChartRelations: render antes, handlers después).
  chart.on("click", (params) => {
    const datum = params?.data;
    if (!datum) return;
    if (params?.seriesType === "lines") {
      const nextKey = pickWorkspaceEdgeFocusKey(datum, activeWorkspaceRelationKey);
      if (!nextKey) return;
      activeWorkspaceRelationKey = nextKey;
      initWorkspaceRelationsChart(chart, payload, {
        ...options,
        combinedView,
      });
      return;
    }
    if (!datum.isRelationNode) return;
    if (Number(datum.degree || 0) < 1) return;
    activeWorkspaceRelationKey = activeWorkspaceRelationKey === datum.key ? null : datum.key;
    initWorkspaceRelationsChart(chart, payload, {
      ...options,
      combinedView,
    });
  });

  chart.off("legendselectchanged");
  chart.on("legendselectchanged", (params) => {
    if (!filtered.edges.length) return;
    const sel = params?.selected || {};
    const visibleLabels = new Set(
      Object.keys(sel).filter((name) => sel[name]).map((name) => String(name)),
    );
    const visibleNodeKeys = new Set(
      payload.nodes
        .filter((node) => visibleLabels.has(String(node.label ?? "")))
        .map((node) => String(node.key ?? "")),
    );
    const filteredEdgeData = buildEdgeSeriesData(filtered.edges, nodeMap, visibleNodeKeys);
    chart.setOption(
      {
        ...animationGlobals,
        series: [{ id: "workspace-relations-edges", data: filteredEdgeData }],
      },
      { notMerge: false, lazyUpdate: false },
    );
  });
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

function workspaceCrossCurvenessBoost(edge) {
  const mix = String(edge?.endpoint_model_mix || "");
  if (mix === "tech_cmt") return 1;
  if (mix === "joint_mix") return 0.55;
  return 0;
}

function pickWorkspaceEdgeFocusKey(edge, currentSelectedKey) {
  const source = String(edge?.source || "").trim();
  const target = String(edge?.target || "").trim();
  if (!source || !target) return "";
  if (currentSelectedKey === source) return target;
  if (currentSelectedKey === target) return source;
  return source;
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
          const sk = String(edge.source || "");
          const tk = String(edge.target || "");
          const boost = workspaceCrossCurvenessBoost(edge);
          return {
            ...edge,
            sourceEntity: edge.source_entity,
            targetEntity: edge.target_entity,
            coords: [
              [Number(source.x || 0), Number(source.y || 0)],
              [Number(target.x || 0), Number(target.y || 0)],
            ],
            lineStyle: {
              color: EDGE_COLORS[edge.tier],
              width: 2.4,
              opacity: 1,
              curveness: relationLineCurveness(sk, tk, boost),
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
        selected: node.key === selectedKey,
      })),
    edges: connectedEdges,
  };
}

function buildNodeSeries(nodes, opts = {}) {
  const combinedView = Boolean(opts.combinedView);
  const articleLayout = Boolean(opts.articleLayout);
  const referenceMax = articleLayout
    ? Math.max(2, ...nodes.map((node) => Number(node.frequency || 1)))
    : 1;
  const groups = {};

  nodes.forEach((node) => {
    const label = node.label || "UNKNOWN";
    if (!groups[label]) groups[label] = [];
    const origin = String(node.dominant_origin || node.dominantOrigin || "joint").toLowerCase();
    const frequency = Number(node.frequency || 1);
    groups[label].push({
      value: [Number(node.x || 0), Number(node.y || 0)],
      key: node.key,
      entity: node.entity,
      entityType: label,
      dominantOrigin: origin,
      dominant_origin: origin,
      frequency,
      articleCount: Number(node.article_count ?? node.articleCount ?? 1),
      degree: Number(node.degree || 0),
      symbolSize: articleLayout
        ? articleRelationSymbolSize(frequency, referenceMax)
        : workspaceAggregateSymbolSize(node),
      isRelationNode: true,
      selected: Boolean(node.selected),
    });
  });

  return Object.keys(groups).map((label) => ({
    id: `ws-rel-${label}`,
    name: label,
    type: "scatter",
    z: 3,
    data: groups[label],
    symbol: "circle",
    symbolSize: (_value, params) => params?.data?.symbolSize ?? 14,
    itemStyle: {
      color: combinedView
        ? ambosSeriesLegendFill(label, groups[label].map((n) => n.dominantOrigin ?? "joint"))
        : getColorForLabel(label),
      opacity: 1,
      borderColor: "#ffffff",
      borderWidth: 1.2,
    },
    label: {
      show: true,
      formatter: (params) => String(params?.data?.entity || ""),
      position: "top",
      distance: 6,
      fontSize: 10,
      color: ENTITY_POINT_LABEL_COLOR,
      fontWeight: 500,
    },
    emphasis: {
      focus: "none",
      scale: true,
    },
    encode: { x: 0, y: 1 },
  })).map((series) => ({
    ...series,
    data: series.data.map((node) => {
      const fill = combinedView
        ? ambosOriginFillColor(node.entityType, node.dominantOrigin)
        : getColorForLabel(node.entityType);
      return {
        ...node,
        itemStyle: {
          color: fill,
          opacity: 1,
          borderColor: node.selected ? "#212529" : "#ffffff",
          borderWidth: node.selected ? 2.4 : 1.2,
        },
        label: {
          color: ENTITY_POINT_LABEL_COLOR,
          fontWeight: node.selected ? 600 : 500,
        },
      };
    }),
  }));
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
          fill: "#374151",
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
              fill: ENTITY_POINT_LABEL_COLOR,
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
          fill: "#374151",
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
