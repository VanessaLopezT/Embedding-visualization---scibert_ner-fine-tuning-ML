/**
 * Utilidades compartidas para rangos de ejes value (t-SNE, relaciones, etc.).
 */

/** Nombres de entidad sobre puntos: casi negro para leer bien sobre #fafafa */
export const ENTITY_POINT_LABEL_COLOR = "#111827";
/** Marcas numéricas de ejes (workspace / gráficas con chartAxisUtils) */
export const WORKSPACE_AXIS_TICK_COLOR = "#374151";

/**
 * Margen proporcional por eje: los símbolos se miden en px y sobresalen del bbox de datos.
 */
export function padAxisRange2d(range, padRatio = 0.07) {
  if (!range) return null;
  const xMin = Number(range.xMin);
  const xMax = Number(range.xMax);
  const yMin = Number(range.yMin);
  const yMax = Number(range.yMax);
  if (![xMin, xMax, yMin, yMax].every(Number.isFinite)) return range;
  const pw = Math.max(xMax - xMin, 1e-12) * padRatio;
  const ph = Math.max(yMax - yMin, 1e-12) * padRatio;
  return {
    xMin: xMin - pw,
    xMax: xMax + pw,
    yMin: yMin - ph,
    yMax: yMax + ph,
  };
}

/**
 * Redondea [min, max] a límites legibles para marcas (5, 10, 0.5, 2, …).
 */
export function niceValueRange(min, max, targetParts = 6) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { min, max };
  if (Math.abs(max - min) < 1e-15) {
    const d = Math.abs(min) > 1e-6 ? Math.abs(min) * 0.06 : 0.5;
    return niceValueRange(min - d, max + d, targetParts);
  }
  const span = max - min;
  const roughStep = span / Math.max(2, targetParts);
  const exp = Math.floor(Math.log10(Math.max(roughStep, 1e-12)));
  const magnitude = 10 ** exp;
  const frac = roughStep / magnitude;
  let niceFrac = 10;
  if (frac <= 1) niceFrac = 1;
  else if (frac <= 2) niceFrac = 2;
  else if (frac <= 5) niceFrac = 5;
  const step = niceFrac * magnitude;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  if (hi <= lo) return { min: lo, max: lo + step };
  return { min: lo, max: hi };
}

/** Rango congelado desde otra vista: margen para bolitas grandes + ticks redondeados. */
/**
 * Ejes numéricos legibles para workspace (marca uniforme; evita 10, 20, 26.7…).
 * Devuelve min/max ampliados al siguiente múltiplo del paso «nice» y el intervalo entre marcas.
 */
export function niceLinearAxisTicks(minVal, maxVal, splitCount = 5) {
  let lo = Number(minVal);
  let hi = Number(maxVal);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
  if (hi < lo) [lo, hi] = [hi, lo];
  let span = hi - lo;
  if (span < 1e-15) {
    const pad = Math.max(Math.abs(lo), 1) * 0.08;
    lo -= pad;
    hi += pad;
    span = hi - lo;
  }
  const roughStep = span / Math.max(2, splitCount);
  const exp = Math.floor(Math.log10(Math.max(roughStep, 1e-12)));
  const magnitude = 10 ** exp;
  const frac = roughStep / magnitude;
  let niceFrac = 10;
  if (frac <= 1) niceFrac = 1;
  else if (frac <= 2) niceFrac = 2;
  else if (frac <= 5) niceFrac = 5;
  const interval = niceFrac * magnitude;
  const niceMin = Math.floor(lo / interval - 1e-9) * interval;
  const niceMax = Math.ceil(hi / interval + 1e-9) * interval;
  if (niceMax <= niceMin) {
    return { min: niceMin, max: niceMin + interval, interval };
  }
  return { min: niceMin, max: niceMax, interval };
}

/** Formateador coherente con `interval` de niceLinearAxisTicks. */
export function formatAxisTick(interval) {
  const step = Number(interval);
  if (!Number.isFinite(step) || step <= 0) {
    return (value) => String(value);
  }
  const tol = Math.max(step * 1e-9, Number.EPSILON * 100 * Math.abs(step));
  const snapToGrid = (x) => {
    const q = Math.round(x / step) * step;
    return Math.abs(x - q) <= tol ? q : x;
  };
  if (step >= 1) {
    return (value) => {
      const x = snapToGrid(Number(value));
      return Number.isFinite(x) ? String(Math.round(x)) : String(value);
    };
  }
  const decimals = Math.min(4, Math.max(1, 1 - Math.floor(Math.log10(step))));
  return (value) => {
    const x = snapToGrid(Number(value));
    return Number.isFinite(x) ? Number(x).toFixed(decimals) : String(value);
  };
}

export function normalizeArticleFrozenAxis(axisRange, padRatio = 0.07) {
  if (!axisRange) return null;
  if (![axisRange.xMin, axisRange.xMax, axisRange.yMin, axisRange.yMax].every(Number.isFinite)) {
    return null;
  }
  const padded = padAxisRange2d(axisRange, padRatio);
  if (!padded) return axisRange;
  const nx = niceValueRange(padded.xMin, padded.xMax);
  const ny = niceValueRange(padded.yMin, padded.yMax);
  return {
    xMin: nx.min,
    xMax: nx.max,
    yMin: ny.min,
    yMax: ny.max,
  };
}

/**
 * Expande el rectángulo de datos a intervalos [-M,M] por eje (con margen padRatio).
 * Útil cuando los puntos ya tienen media ~0 pero la dispersión es asimétrica (vista ambos).
 */
export function symmetricWorkspaceExtent(extent, padRatio = 0.07) {
  if (!extent) return null;
  const mx = Math.max(Math.abs(Number(extent.xMin)), Math.abs(Number(extent.xMax)));
  const my = Math.max(Math.abs(Number(extent.yMin)), Math.abs(Number(extent.yMax)));
  let hx = mx;
  let hy = my;
  if (hx < 1e-12 && hy < 1e-12) {
    hx = 1;
    hy = 1;
  }
  const px = hx * padRatio;
  const py = hy * padRatio;
  return {
    xMin: -(hx + px),
    xMax: hx + px,
    yMin: -(hy + py),
    yMax: hy + py,
  };
}

/**
 * Vista workspace combinada (ambos): cuadrado centrado en la nube de puntos en lugar del origen,
 * para no desperdiciar franjas vacías cuando la nube no está centrada en (0,0).
 */
export function squarifiedWorkspaceExtent(extent, padRatio = 0.07) {
  if (!extent) return null;
  const xmin = Number(extent.xMin);
  const xmax = Number(extent.xMax);
  const ymin = Number(extent.yMin);
  const ymax = Number(extent.yMax);
  if (![xmin, xmax, ymin, ymax].every(Number.isFinite)) return null;
  const cx = (xmin + xmax) / 2;
  const cy = (ymin + ymax) / 2;
  const halfwx = Math.max((xmax - xmin) / 2, 1e-9);
  const halfhy = Math.max((ymax - ymin) / 2, 1e-9);
  const half = Math.max(halfwx, halfhy) * (1 + padRatio);
  return {
    xMin: cx - half,
    xMax: cx + half,
    yMin: cy - half,
    yMax: cy + half,
  };
}

/** Bounding box de nodos `{ x, y }` (p. ej. puntos del workspace). */
export function extentFromScatterNodes(nodes) {
  const xs = [];
  const ys = [];
  for (const n of nodes || []) {
    const x = Number(n?.x);
    const y = Number(n?.y);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      xs.push(x);
      ys.push(y);
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

/**
 * Misma clave de agregación que `tsneChartRelations` / `buildRelationModel` (entidad canónica).
 */
export function normalizeEntityAggregateKey(raw) {
  return String(raw || "")
    .toLowerCase()
    .replace(/[“”"']/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Ejes workspace: pad proporcional + niceLinearAxisTicks.
 * @param symmetricOrigin `false` bbox+pad · `'origin'` simétrico en 0 · `'square'` cuadrado centrado en la nube (ambos workspace).
 */
export function workspaceScatterAxesFromExtent(
  extent,
  padRatio = 0.07,
  splitCount = 6,
  symmetricOrigin = false,
) {
  if (!extent) return null;
  let padded =
    symmetricOrigin === "square"
      ? squarifiedWorkspaceExtent(extent, padRatio)
      : symmetricOrigin
        ? symmetricWorkspaceExtent(extent, padRatio)
        : padAxisRange2d(extent, padRatio);
  if (!padded) return null;
  const nx = niceLinearAxisTicks(padded.xMin, padded.xMax, splitCount);
  const ny = niceLinearAxisTicks(padded.yMin, padded.yMax, splitCount);
  if (!nx || !ny) return null;
  const tickLabelStyle = {
    color: WORKSPACE_AXIS_TICK_COLOR,
    fontSize: 11,
  };
  const baseAxis = (name, nameGap) => ({
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
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: tickLabelStyle,
    splitLine: { show: true, lineStyle: { color: "#f0f0f0" } },
  });
  /** Sin `interval` fijo: con dataZoom dentro, el paso bloqueaba el escalado como en articulo (#tsne). */
  const simpleTick = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v ?? "");
    return String(Number(n.toFixed(6)));
  };
  return {
    xAxis: {
      ...baseAxis("Dimension 1", 30),
      min: nx.min,
      max: nx.max,
      axisLabel: { ...tickLabelStyle, formatter: simpleTick },
    },
    yAxis: {
      ...baseAxis("Dimension 2", 40),
      min: ny.min,
      max: ny.max,
      axisLabel: { ...tickLabelStyle, formatter: simpleTick },
    },
  };
}

/**
 * Igual que `tsneChart.js` (vista artículo): dos dataZoom `inside` separados (X e Y).
 * El zoom unificado XY en workspace bloqueaba el desplazamiento vertical con rueda+zoom.
 */
export function workspaceChartDataZoomInside() {
  return [
    {
      type: "inside",
      xAxisIndex: [0],
      start: 0,
      end: 100,
      zoomOnMouseWheel: true,
      moveOnMouseMove: true,
      moveOnMouseWheel: false,
      filterMode: "none",
      zoomLock: false,
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
      zoomLock: false,
    },
  ];
}

/** Misma fórmula que workspaceAggregateChart para tamaño de símbolo por entidad agregada. */
export function workspaceAggregateSymbolSize(node) {
  const frequency = Math.max(1, Number(node?.frequency ?? 1));
  const articleCount = Math.max(1, Number(node?.article_count ?? node?.articleCount ?? 1));
  const size =
    13 +
    Math.log2(frequency + 1) * 4.6 +
    Math.log2(articleCount + 1) * 3.8;
  return Math.max(13, Math.min(42, size));
}

/**
 * Leyenda de categorías NER en workspace (idem en agregados y relaciones): desplaza el bloque a la derecha
 * para no solaparlo con `#workspace-relations-filter-controls` (top-izquierda).
 * Con `center` el borde izquierdo queda ~ (100 − width) / 2 (~24 % del ancho con leyenda ~52 %).
 */
export const WORKSPACE_CATEGORY_LEGEND_LEFT = "30%";
export const WORKSPACE_CATEGORY_LEGEND_WIDTH = "52%";
