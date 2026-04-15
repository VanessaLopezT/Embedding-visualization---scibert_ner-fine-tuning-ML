/**
 * tsneChartRelations.js
 * Vista de relaciones semantico-contextuales derivadas del tsne ya cargado.
 *
 * NO recalcula NER ni embeddings. Trabaja con el JSON existente:
 *   - agrega ocurrencias por entidad
 *   - posiciona cada nodo en el centroide de sus puntos t-SNE
 *   - calcula relaciones por coocurrencia en frase/chunk
 *
 * La salida es una grafica independiente que reutiliza la estetica de las
 * vistas actuales para no alterar tamano ni layout general.
 */

import { getColorForLabel } from "./categoryColors.js";

let activeRelationKey = null;
const ARTICLE_LEGEND_WIDTH_TECH = "auto";
const ARTICLE_LEGEND_WIDTH_CMT = "56%";
const ARTICLE_LEGEND_WIDTH_WRAP = "52%";

const DEFAULT_OPTIONS = {
  minEntityFrequency: 1,
  minSentenceCooccurrence: 2,
  scoreThreshold: 0.24,
  maxEdges: 90,
  filterMode: "all",
};

export function initTSNERelationsChart(chart, data, axisRange = null, options = {}) {
  const safeData = Array.isArray(data) ? data : [];
  const relationOptions = {
    ...DEFAULT_OPTIONS,
    ...sanitizeOptions(options),
  };
  if (typeof options.onRenderSummary === "function") {
    relationOptions.onRenderSummary = options.onRenderSummary;
  }

  renderRelations(chart, safeData, axisRange, relationOptions);

  chart.off("mouseover");
  chart.off("mouseout");
  chart.off("click");

  chart.on("mouseover", (params) => {
    const datum = params?.data;
    if (!datum || !datum.isRelationNode) return;
    const id = pickVisibleEntityId(datum.ids);
    if (id !== undefined) highlightEntityInPanel(id, datum.entity);
  });

  chart.on("mouseout", () => {
    clearHighlightInPanel();
  });

  chart.on("click", (params) => {
    const datum = params?.data;
    if (!datum || !datum.isRelationNode) return;
    const id = pickVisibleEntityId(datum.ids);
    if (id !== undefined) highlightEntityInPanel(id, datum.entity);
    const clickedKey = String(datum.key || "");
    if (!clickedKey) return;
    activeRelationKey = activeRelationKey === clickedKey ? null : clickedKey;
    renderRelations(chart, safeData, axisRange, relationOptions);
  });

  window.addEventListener("resize", () => chart.resize());
}

export function resetRelationsSelection() {
  activeRelationKey = null;
}

function sanitizeOptions(options) {
  return {
    minEntityFrequency: clampInt(options.minEntityFrequency, 1, 9999, DEFAULT_OPTIONS.minEntityFrequency),
    minSentenceCooccurrence: Math.max(
      DEFAULT_OPTIONS.minSentenceCooccurrence,
      clampInt(options.minSentenceCooccurrence, 1, 99, DEFAULT_OPTIONS.minSentenceCooccurrence),
    ),
    scoreThreshold: Math.max(
      DEFAULT_OPTIONS.scoreThreshold,
      clampNumber(options.scoreThreshold, 0, 1, DEFAULT_OPTIONS.scoreThreshold),
    ),
    maxEdges: clampInt(options.maxEdges, 10, 5000, DEFAULT_OPTIONS.maxEdges),
    filterMode: ["all", "connected", "low", "medium", "high"].includes(options.filterMode) ? options.filterMode : "all",
  };
}

function renderRelations(chart, data, axisRange, options) {
  const model = buildRelationModel(data, options);
  const allQuartiles = computeScoreQuartiles(model.edges);
  const tieredModel = {
    ...model,
    edges: model.edges.map((edge) => ({
      ...edge,
      tier: classifyEdge(edge.score, allQuartiles),
    })),
  };
  const visibleModel = applyVisibilityFilter(tieredModel, options.filterMode);
  const filtered = applySelection(visibleModel, activeRelationKey, options.filterMode);
  
  // Usar cuartiles originales para mantener colores consistentes por tier (low=azul, medium=morado, high=magenta)
  const series = buildNodeSeries(filtered.nodes);
  const edgeSeries = buildEdgeSeries(filtered.edges, allQuartiles);
  const relationLegend = filtered.edges.length ? buildRelationLegend() : buildNoRelationsGraphic(options.filterMode);
  const legendConfig = buildArticleLegendConfig(filtered.nodes.map(node => node?.label));
  const hasRenderableRelations = filtered.edges.length > 0;

  const option = {
    animation: true,
    animationDuration: 350,
    animationDurationUpdate: 350,
    animationEasing: "cubicOut",
    tooltip: {
      show: true,
      formatter: (params) => {
        if (params?.seriesType === "lines") {
          const edge = params.data || {};
          const edgeColor = String(edge?.lineStyle?.color || "#495057");
          return [
            `<b style="color:${escapeHtml(edgeColor)};">${escapeHtml(edge.sourceEntity || "")} ↔ ${escapeHtml(edge.targetEntity || "")}</b>`,
            `Afinidad: ${formatScore(edge.score)}`,
            `Coocurrencias en frase: ${Number(edge.sentenceCooccurrence || 0)}`,
            `Solapamiento en chunk: ${formatScore(edge.chunkJaccard || 0)}`,
            `Similitud de contexto: ${formatScore(edge.profileSimilarity || 0)}`,
            `NPMI contextual: ${formatScore(edge.sentenceNpmi || 0)}`,
          ].join("<br/>");
        }

        const node = params?.data || {};
        return [
          `<b>${escapeHtml(node.entity || "")}</b>`,
          `Tipo: ${escapeHtml(node.entityType || "")}`,
        ].join("<br/>");
      }
    },
    toolbox: {
      feature: {
        dataZoom: {},
        restore: {
          onclick: () => { activeRelationKey = null; }
        },
        saveAsImage: {}
      },
      right: 20,
      top: 20
    },
    legend: {
      top: 42,
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
      itemHeight: 11
    },
    grid: {
      left: 60,
      right: 30,
      bottom: 40,
      top: 122,
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
    xAxis: hasRenderableRelations ? {
      type: "value",
      ...(axisRange ? { min: axisRange.xMin, max: axisRange.xMax } : {}),
      name: "Dimension 1",
      nameLocation: "middle",
      nameGap: 30,
      axisLine: { show: false, lineStyle: { color: "#000000" } },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: "#f0f0f0" }
      }
    } : {
      type: "value",
      show: false,
    },
    yAxis: hasRenderableRelations ? {
      type: "value",
      ...(axisRange ? { min: axisRange.yMin, max: axisRange.yMax } : {}),
      name: "Dimension 2",
      nameLocation: "middle",
      nameGap: 40,
      axisLine: { show: false, lineStyle: { color: "#000000" } },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: "#f0f0f0" }
      }
    } : {
      type: "value",
      show: false,
    },
    graphic: relationLegend,
    series: hasRenderableRelations ? [edgeSeries, ...series] : []
  };

  chart.setOption(option, true);

  if (typeof options.onRenderSummary === "function") {
    queueMicrotask(() => {
      options.onRenderSummary({
        visibleNodeCount: filtered.nodes.length,
        visibleEdgeCount: filtered.edges.length,
      });
    });
  }

  chart.off("legendselectchanged");
  chart.on("legendselectchanged", (params) => {
    const selectedLabels = Object.keys(params.selected).filter((label) => params.selected[label]);
    const visibleNodeKeys = new Set(
      filtered.nodes
        .filter((node) => selectedLabels.includes(node.label))
        .map((node) => node.key)
    );
    chart.setOption({
      series: [
        { id: edgeSeries.id, data: buildEdgeSeries(filtered.edges, null, visibleNodeKeys).data }
      ]
    });
  });
}

function buildArticleLegendConfig(labels = []) {
  const uniqueLabels = Array.from(new Set(labels.map(label => String(label || "").trim()).filter(Boolean)));
  const usesCmtLabels = labels.some(label => /\/| and |oncology|treatment/i.test(String(label || "")));
  if (usesCmtLabels) {
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

function buildRelationModel(data, options) {
  const aggregateMap = new Map();
  const sentenceEntityMap = new Map();
  const chunkEntityMap = new Map();

  data.forEach((point) => {
    const entity = String(point?.entity || "").trim();
    if (!entity) return;

    const key = normalizeEntity(entity);
    if (!aggregateMap.has(key)) {
      aggregateMap.set(key, {
        key,
        entity,
        points: [],
        ids: [],
        labelCounts: new Map(),
        sentenceSet: new Set(),
        chunkSet: new Set(),
      });
    }

    const bucket = aggregateMap.get(key);
    bucket.points.push(point);
    if (point?.id !== undefined) bucket.ids.push(point.id);
    const label = String(point?.label || "TECHNIQUE");
    bucket.labelCounts.set(label, (bucket.labelCounts.get(label) || 0) + 1);

    if (point?.sentence_id !== undefined && point?.sentence_id !== null) {
      const sentenceKey = String(point.sentence_id);
      bucket.sentenceSet.add(sentenceKey);
      if (!sentenceEntityMap.has(sentenceKey)) sentenceEntityMap.set(sentenceKey, new Set());
      sentenceEntityMap.get(sentenceKey).add(key);
    }
    if (point?.text_index !== undefined && point?.text_index !== null) {
      const chunkKey = String(point.text_index);
      bucket.chunkSet.add(chunkKey);
      if (!chunkEntityMap.has(chunkKey)) chunkEntityMap.set(chunkKey, new Set());
      chunkEntityMap.get(chunkKey).add(key);
    }
  });

  let nodes = Array.from(aggregateMap.values())
    .map((item) => {
      const frequency = item.points.length;
      const centroid = item.points.reduce((acc, point) => {
        acc.x += Number(point?.x || 0);
        acc.y += Number(point?.y || 0);
        return acc;
      }, { x: 0, y: 0 });

      centroid.x /= Math.max(frequency, 1);
      centroid.y /= Math.max(frequency, 1);

      return {
        key: item.key,
        entity: pickDisplayEntity(item.points, item.entity),
        label: dominantLabel(item.labelCounts),
        frequency,
        sentenceCount: item.sentenceSet.size,
        chunkCount: item.chunkSet.size,
        x: centroid.x,
        y: centroid.y,
        ids: item.ids,
        sentences: item.sentenceSet,
        chunks: item.chunkSet,
        sentenceProfile: buildContextProfile(item.sentenceSet, sentenceEntityMap, item.key),
        chunkProfile: buildContextProfile(item.chunkSet, chunkEntityMap, item.key),
        degree: 0,
      };
    })
    .filter((node) => node.frequency >= options.minEntityFrequency)
    .sort((a, b) => {
      if (b.frequency !== a.frequency) return b.frequency - a.frequency;
      return a.entity.localeCompare(b.entity);
    });

  const totals = {
    totalSentenceContexts: Math.max(1, sentenceEntityMap.size),
    totalChunkContexts: Math.max(1, chunkEntityMap.size),
  };
  const edges = [];
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const edge = buildEdge(nodes[i], nodes[j], options, totals);
      if (!edge) continue;
      edges.push(edge);
      nodes[i].degree += 1;
      nodes[j].degree += 1;
    }
  }

  edges.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    if (b.sentenceCooccurrence !== a.sentenceCooccurrence) return b.sentenceCooccurrence - a.sentenceCooccurrence;
    return a.sourceEntity.localeCompare(b.sourceEntity);
  });

  if (edges.length > options.maxEdges) {
    const allowed = new Set(edges.slice(0, options.maxEdges).map((edge) => edge.key));
    nodes = nodes.map((node) => ({
      ...node,
      degree: edges.reduce((acc, edge) => {
        if (!allowed.has(edge.key)) return acc;
        return edge.source === node.key || edge.target === node.key ? acc + 1 : acc;
      }, 0)
    }));
  }

  return {
    nodes,
    edges: edges.slice(0, options.maxEdges),
    totalSentenceContexts: totals.totalSentenceContexts,
    totalChunkContexts: totals.totalChunkContexts,
  };
}

function buildEdge(sourceNode, targetNode, options, totals = {}) {
  const sentenceIntersection = intersectSize(sourceNode.sentences, targetNode.sentences);
  if (sentenceIntersection < options.minSentenceCooccurrence) return null;

  const sentenceUnion = unionSize(sourceNode.sentences, targetNode.sentences);
  const chunkIntersection = intersectSize(sourceNode.chunks, targetNode.chunks);
  const chunkUnion = unionSize(sourceNode.chunks, targetNode.chunks);

  const sentenceJaccard = sentenceUnion > 0 ? sentenceIntersection / sentenceUnion : 0;
  const chunkJaccard = chunkUnion > 0 ? chunkIntersection / chunkUnion : 0;
  const overlapStrength = sentenceIntersection / Math.max(1, Math.min(sourceNode.sentenceCount, targetNode.sentenceCount));
  const profileSentenceCosine = cosineMapSimilarity(sourceNode.sentenceProfile, targetNode.sentenceProfile);
  const profileChunkCosine = cosineMapSimilarity(sourceNode.chunkProfile, targetNode.chunkProfile);
  const profileSimilarity = (0.7 * profileSentenceCosine) + (0.3 * profileChunkCosine);
  const sentenceNpmi = computeNpmi(
    sentenceIntersection,
    sourceNode.sentenceCount,
    targetNode.sentenceCount,
    totals.totalSentenceContexts || 1,
  );
  const chunkNpmi = computeNpmi(
    chunkIntersection,
    sourceNode.chunkCount,
    targetNode.chunkCount,
    totals.totalChunkContexts || 1,
  );
  const associationStrength = (0.8 * sentenceNpmi) + (0.2 * chunkNpmi);

  // Afinidad agregada por entidad:
  // - relacion directa: comparten frases/chunks
  // - relacion contextual: se parecen sus vecindarios de coocurrencia
  // - asociacion semantico-contextual: NPMI favorece pares que coaparecen
  //   mas de lo esperado por frecuencia marginal
  const score =
    (0.25 * sentenceJaccard) +
    (0.15 * chunkJaccard) +
    (0.15 * overlapStrength) +
    (0.20 * profileSimilarity) +
    (0.25 * associationStrength);
  if (score < options.scoreThreshold) return null;

  return {
    key: `${sourceNode.key}__${targetNode.key}`,
    source: sourceNode.key,
    target: targetNode.key,
    sourceEntity: sourceNode.entity,
    targetEntity: targetNode.entity,
    coords: [[sourceNode.x, sourceNode.y], [targetNode.x, targetNode.y]],
    score,
    sentenceCooccurrence: sentenceIntersection,
    sentenceJaccard,
    chunkJaccard,
    profileSimilarity,
    sentenceNpmi,
    chunkNpmi,
    lineWidth: edgeWidthFromScore(score),
    opacity: edgeOpacityFromScore(score),
  };
}

function applySelection(model, selectedKey, filterMode) {
  if (!selectedKey) return model;
  
  // Filtrar aristas conectadas al nodo seleccionado
  let edgeSet = model.edges.filter((edge) => edge.source === selectedKey || edge.target === selectedKey);
  
  // Si hay un filtro de tier activo (low, medium, high), aplicarlo también
  if (filterMode === "low" || filterMode === "medium" || filterMode === "high") {
    edgeSet = edgeSet.filter((edge) => edge.tier === filterMode);
  }
  
  const connectedKeys = new Set([selectedKey]);
  edgeSet.forEach((edge) => {
    connectedKeys.add(edge.source);
    connectedKeys.add(edge.target);
  });

  return {
    nodes: model.nodes
      .filter((node) => connectedKeys.has(node.key))
      .map((node) => ({
        ...node,
        selected: node.key === selectedKey,
      })),
    edges: edgeSet,
  };
}

function applyVisibilityFilter(model, filterMode) {
  if (filterMode !== "connected" && filterMode !== "low" && filterMode !== "medium" && filterMode !== "high") {
    return model;
  }

  const scopedEdges = filterMode === "connected"
    ? model.edges
    : model.edges.filter((edge) => edge.tier === filterMode);

  const connectedKeys = new Set();
  scopedEdges.forEach((edge) => {
    connectedKeys.add(edge.source);
    connectedKeys.add(edge.target);
  });

  return {
    nodes: model.nodes.filter((node) => connectedKeys.has(node.key)),
    edges: scopedEdges,
  };
}

function buildEdgeSeries(edges, quartiles = null, visibleNodeKeys = null) {
  const filteredEdges = Array.isArray(edges)
    ? edges.filter((edge) => {
        if (!visibleNodeKeys) return true;
        return visibleNodeKeys.has(edge.source) && visibleNodeKeys.has(edge.target);
      })
    : [];
  // Usar cuartiles proporcionados o calcular si no se pasaron
  const edgeQuartiles = quartiles || computeScoreQuartiles(filteredEdges);
  return {
    id: "relations-edges",
    type: "lines",
    coordinateSystem: "cartesian2d",
    z: 1,
    silent: false,
    polyline: false,
    effect: { show: false },
    showInLegend: false,
    showLegendSymbol: false,
    legendHoverLink: false,
    lineStyle: {
      width: 2.4,
      opacity: 1,
      color: "#7f8c8d",
      curveness: 0.08,
    },
    data: filteredEdges.map((edge) => ({
      ...edge,
      coords: edge.coords,
      lineStyle: {
        width: 2.4,
        opacity: edge.muted ? 0.1 : 1,
        color: edge.muted ? "#d6dde3" : edgeColorFromQuartiles(edge.score, edgeQuartiles),
        curveness: 0.08,
      }
    })),

    tooltip: { show: true }
  };
}

function buildNodeSeries(nodes) {
  const referenceMax = Math.max(2, ...nodes.map((node) => node.frequency || 1));
  const groups = {};

  nodes.forEach((node) => {
    if (!groups[node.label]) groups[node.label] = [];
    groups[node.label].push({
      value: [node.x, node.y],
      key: node.key,
      entity: node.entity,
      entityType: node.label,
      frequency: node.frequency,
      sentenceCount: node.sentenceCount,
      degree: node.degree,
      ids: node.ids,
      symbolSize: nodeSizeFromFrequency(node.frequency, referenceMax),
      isRelationNode: true,
      muted: Boolean(node.muted),
      selected: Boolean(node.selected),
    });
  });

  const selectionActive = Boolean(activeRelationKey);

  return Object.keys(groups).map((label) => ({
    id: `rel-${label}`,
    name: label,
    type: "scatter",
    z: 3,
    data: groups[label],
    symbolSize: (_value, params) => params?.data?.symbolSize ?? 14,
    itemStyle: {
      color: getColorForLabel(label),
      opacity: 1,
      borderColor: "#ffffff",
      borderWidth: 1.2,
    },
    label: {
      show: true,
      formatter: (params) => {
        return String(params?.data?.entity || "");
      },
      position: "top",
      distance: 6,
      fontSize: 10,
      color: "#333",
      fontWeight: "normal"
    },
    emphasis: {
      focus: "none",
      scale: true,
    },
    encode: { x: 0, y: 1 },
  })).map((series) => ({
    ...series,
    data: series.data.map((node) => ({
      ...node,
      itemStyle: {
        color: getColorForLabel(node.entityType),
        opacity: selectionActive ? 1 : (node.muted ? 0.22 : 1),
        borderColor: node.selected ? "#212529" : "#ffffff",
        borderWidth: node.selected ? 2.4 : 1.2,
      },
      label: {
        color: selectionActive ? "#333" : (node.muted ? "#9aa1a7" : "#333"),
        fontWeight: node.selected ? 600 : 400,
      }
    }))
  }));
}

function nodeSizeFromFrequency(frequency, referenceMax) {
  if (frequency <= 1) return 16;
  if (referenceMax <= 1) return 16;

  const minRepeated = 2;
  const minSize = 20;
  const maxSize = 60;
  const alpha = 0.65;

  if (referenceMax <= minRepeated) return minSize;

  const logMin = Math.log(minRepeated);
  const logMax = Math.log(referenceMax);
  const logF = Math.log(Math.max(frequency, minRepeated));
  const t = (logF - logMin) / Math.max(logMax - logMin, 1e-9);
  return minSize + (maxSize - minSize) * Math.pow(Math.max(0, Math.min(1, t)), alpha);
}

function edgeWidthFromScore(score) {
  return 2.4;
}

function edgeOpacityFromScore(score) {
  return 1;
}

function computeScoreQuartiles(edges) {
  const scores = edges
    .map((edge) => Number(edge?.score || 0))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);

  if (!scores.length) {
    return { q1: 0.33, q2: 0.66, q3: 1 };
  }

  return {
    q1: percentile(scores, 0.33),
    q2: percentile(scores, 0.66),
    q3: percentile(scores, 1),
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

function edgeColorFromQuartiles(score, quartiles) {
  const s = Number(score || 0);
  if (s <= quartiles.q1) return "#7dd3fc";
  if (s <= quartiles.q2) return "#6366f1";
  return "#c026d3";
}

function classifyEdge(score, quartiles) {
  const s = Number(score || 0);
  if (s <= quartiles.q1) return "low";
  if (s <= quartiles.q2) return "medium";
  return "high";
}

function buildRelationLegend() {
  const items = [
    { color: "#7dd3fc", label: "Baja" },
    { color: "#6366f1", label: "Media" },
    { color: "#c026d3", label: "Alta" },
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
          x: 0, y: 1,
          text: "Relación:",
          fill: "#6b7280",
          font: "11px sans-serif",
        },
      },
      ...items.flatMap((item, index) => {
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
              x: x + 20, y: 1,
              text: item.label,
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

function dominantLabel(labelCounts) {
  let bestLabel = "TECHNIQUE";
  let bestCount = -1;
  labelCounts.forEach((count, label) => {
    if (count > bestCount) {
      bestCount = count;
      bestLabel = label;
    }
  });
  return bestLabel;
}

function pickDisplayEntity(points, fallback) {
  const counts = new Map();
  points.forEach((point) => {
    const entity = String(point?.entity || "").trim();
    if (!entity) return;
    counts.set(entity, (counts.get(entity) || 0) + 1);
  });

  let best = String(fallback || "").trim();
  let bestCount = -1;
  counts.forEach((count, entity) => {
    if (count > bestCount) {
      best = entity;
      bestCount = count;
    }
  });
  return best;
}

function normalizeEntity(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[“”"']/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function buildContextProfile(contextSet, contextEntityMap, selfKey) {
  const profile = new Map();
  contextSet.forEach((contextKey) => {
    const members = contextEntityMap.get(contextKey);
    if (!members) return;
    members.forEach((memberKey) => {
      if (memberKey === selfKey) return;
      profile.set(memberKey, (profile.get(memberKey) || 0) + 1);
    });
  });
  return profile;
}

function cosineMapSimilarity(left, right) {
  if (!left.size || !right.size) return 0;

  let dot = 0;
  let leftNormSq = 0;
  let rightNormSq = 0;

  left.forEach((value, key) => {
    leftNormSq += value * value;
    const other = right.get(key) || 0;
    dot += value * other;
  });
  right.forEach((value) => {
    rightNormSq += value * value;
  });

  if (leftNormSq <= 0 || rightNormSq <= 0) return 0;
  return dot / (Math.sqrt(leftNormSq) * Math.sqrt(rightNormSq));
}

function computeNpmi(jointCount, leftCount, rightCount, totalContexts) {
  if (jointCount <= 0 || leftCount <= 0 || rightCount <= 0 || totalContexts <= 0) return 0;
  const pxy = jointCount / totalContexts;
  const px = leftCount / totalContexts;
  const py = rightCount / totalContexts;
  if (pxy <= 0 || px <= 0 || py <= 0) return 0;

  const pmi = Math.log(pxy / (px * py));
  const denom = -Math.log(pxy);
  if (!Number.isFinite(pmi) || !Number.isFinite(denom) || denom <= 0) return 0;

  // NPMI teoricamente va de -1 a 1; aqui recortamos a [0,1] porque
  // solo nos interesan asociaciones positivas y estables para el grafo.
  return Math.max(0, Math.min(1, pmi / denom));
}

function intersectSize(left, right) {
  if (!left.size || !right.size) return 0;
  const [small, large] = left.size <= right.size ? [left, right] : [right, left];
  let count = 0;
  small.forEach((item) => {
    if (large.has(item)) count += 1;
  });
  return count;
}

function unionSize(left, right) {
  return left.size + right.size - intersectSize(left, right);
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

function clearHighlightInPanel() {
  document.querySelectorAll(".entity.highlighted").forEach((el) => {
    el.classList.remove("highlighted");
  });
}

function pickVisibleEntityId(ids) {
  if (!Array.isArray(ids) || !ids.length) return undefined;
  for (const id of ids) {
    if (document.querySelector(`[data-id="${id}"]`)) return id;
  }
  return ids[0];
}

function normalizeEntityKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[“”"']/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function clampInt(value, min, max, fallback) {
  const n = Number.parseInt(value, 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

function clampNumber(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

function formatScore(value) {
  return Number(value || 0).toFixed(3);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
