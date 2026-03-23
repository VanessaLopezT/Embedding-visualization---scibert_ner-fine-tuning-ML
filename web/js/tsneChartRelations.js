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

const DEFAULT_OPTIONS = {
  minEntityFrequency: 1,
  topEntities: 40,
  minSentenceCooccurrence: 2,
  scoreThreshold: 0.24,
  maxEdges: 90,
  isolateSelection: false,
};

export function initTSNERelationsChart(chart, data, axisRange = null, options = {}) {
  const safeData = Array.isArray(data) ? data : [];
  const relationOptions = {
    ...DEFAULT_OPTIONS,
    ...sanitizeOptions(options),
  };

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
  });

  window.addEventListener("resize", () => chart.resize());
}

export function resetRelationsSelection() {
  activeRelationKey = null;
}

function sanitizeOptions(options) {
  return {
    minEntityFrequency: clampInt(options.minEntityFrequency, 1, 9999, DEFAULT_OPTIONS.minEntityFrequency),
    topEntities: clampInt(options.topEntities, 5, 300, DEFAULT_OPTIONS.topEntities),
    minSentenceCooccurrence: Math.max(
      DEFAULT_OPTIONS.minSentenceCooccurrence,
      clampInt(options.minSentenceCooccurrence, 1, 99, DEFAULT_OPTIONS.minSentenceCooccurrence),
    ),
    scoreThreshold: Math.max(
      DEFAULT_OPTIONS.scoreThreshold,
      clampNumber(options.scoreThreshold, 0, 1, DEFAULT_OPTIONS.scoreThreshold),
    ),
    maxEdges: clampInt(options.maxEdges, 10, 5000, DEFAULT_OPTIONS.maxEdges),
    isolateSelection: Boolean(options.isolateSelection),
  };
}

function renderRelations(chart, data, axisRange, options) {
  const model = buildRelationModel(data, options);
  const filtered = applySelection(model, activeRelationKey, options);
  const series = buildNodeSeries(filtered.nodes);
  const edgeSeries = buildEdgeSeries(filtered.edges);
  const relationLegend = buildRelationLegend();

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
      top: 22,
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
      top: 82,
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
      name: "Dimension 1",
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
      name: "Dimension 2",
      nameLocation: "middle",
      nameGap: 40,
      axisLine: { show: false, lineStyle: { color: "#000000" } },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: "#f0f0f0" }
      }
    },
    graphic: relationLegend,
    series: [edgeSeries, ...series]
  };

  chart.setOption(option, true);
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
    })
    .slice(0, options.topEntities);

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

function applySelection(model, selectedKey, options) {
  if (!selectedKey) return model;
  const edgeSet = model.edges.filter((edge) => edge.source === selectedKey || edge.target === selectedKey);
  if (!options.isolateSelection) {
    return {
      nodes: model.nodes.map((node) => ({
        ...node,
        muted: node.key !== selectedKey && !edgeSet.some((edge) => edge.source === node.key || edge.target === node.key),
        selected: node.key === selectedKey,
      })),
      edges: model.edges.map((edge) => ({
        ...edge,
        muted: edge.source !== selectedKey && edge.target !== selectedKey,
      })),
    };
  }

  const connectedKeys = new Set([selectedKey]);
  edgeSet.forEach((edge) => {
    connectedKeys.add(edge.source);
    connectedKeys.add(edge.target);
  });

  return {
    nodes: model.nodes
      .filter((node) => connectedKeys.has(node.key))
      .map((node) => ({ ...node, selected: node.key === selectedKey })),
    edges: edgeSet,
  };
}

function buildEdgeSeries(edges) {
  const quartiles = computeScoreQuartiles(edges);
  return {
    id: "relations-edges",
    name: "Relaciones",
    type: "lines",
    coordinateSystem: "cartesian2d",
    z: 1,
    silent: false,
    polyline: false,
    effect: { show: false },
    lineStyle: {
      width: 1.8,
      opacity: 0.18,
      color: "#7f8c8d",
      curveness: 0.08,
    },
    data: edges.map((edge) => ({
      ...edge,
      coords: edge.coords,
      lineStyle: {
        width: 1.8,
        opacity: edge.muted ? Math.max(0.04, edge.opacity * 0.35) : edge.opacity,
        color: edge.muted ? "#d6dde3" : edgeColorFromQuartiles(edge.score, quartiles),
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

  return Object.keys(groups).map((label) => ({
    id: `rel-${label}`,
    name: label,
    type: "scatter",
    z: 3,
    data: groups[label],
    symbolSize: (_value, params) => params?.data?.symbolSize ?? 14,
    itemStyle: {
      color: getColorForLabel(label),
      opacity: 0.95,
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
      focus: "series",
      scale: true,
      itemStyle: {
        borderColor: "#333",
        borderWidth: 2
      }
    },
    encode: { x: 0, y: 1 },
  })).map((series) => ({
    ...series,
    data: series.data.map((node) => ({
      ...node,
      itemStyle: {
        color: getColorForLabel(node.entityType),
        opacity: node.muted ? 0.22 : (node.selected ? 1 : 0.95),
        borderColor: node.selected ? "#212529" : "#ffffff",
        borderWidth: node.selected ? 2.4 : 1.2,
      },
      label: {
        color: node.muted ? "#9aa1a7" : "#333",
        fontWeight: node.selected ? 600 : 400,
      }
    }))
  }));
}

function nodeSizeFromFrequency(frequency, referenceMax) {
  if (frequency <= 1) return 9;
  if (referenceMax <= 1) return 9;

  const minRepeated = 2;
  const minSize = 16;
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
  return 1 + (4 * Math.max(0, Math.min(1, score)));
}

function edgeOpacityFromScore(score) {
  return 0.16 + (0.50 * Math.max(0, Math.min(1, score)));
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
  if (s <= quartiles.q1) return "#7ec8ff";
  if (s <= quartiles.q2) return "#6c63c9";
  return "#8f1d5a";
}

function buildRelationLegend() {
  const items = [
    { color: "#7ec8ff", label: "Relacion baja" },
    { color: "#6c63c9", label: "Relacion media" },
    { color: "#8f1d5a", label: "Relacion alta" },
  ];

  return [{
    type: "group",
    right: 34,
    bottom: 2,
    silent: true,
    children: items.flatMap((item, index) => {
      const y = index * 18;
      return [
        {
          type: "circle",
          shape: { cx: 0, cy: y +10, r: 5 },
          style: {
            fill: item.color,
            stroke: "#ffffff",
            lineWidth: 1,
          }
        },
        {
          type: "text",
          style: {
            x: 12,
            y: y + 4,
            text: item.label,
            fill: "#555",
            font: "12px sans-serif",
          }
        }
      ];
    })
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
