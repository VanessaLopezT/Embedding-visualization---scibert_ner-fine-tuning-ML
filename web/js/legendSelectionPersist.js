/**
 * Persistencia de categorías ocultas en la leyenda ECharts (sessionStorage).
 */

const PREFIX = "echarts.legend.selected.";

export const LEGEND_STORAGE_KEYS = {
  ARTICLE_STANDARD: "article.standard",
  ARTICLE_FREQUENCY: "article.frequency",
  ARTICLE_RELATIONS: "article.relations",
  WORKSPACE_AGGREGATE: "workspace.aggregate",
  WORKSPACE_RELATIONS: "workspace.relations",
};

export function mergeLegendSelected(seriesNames, storageKey) {
  const names = Array.isArray(seriesNames)
    ? [...new Set(seriesNames.filter(Boolean).map(String))]
    : [];
  let saved = {};
  try {
    const raw = sessionStorage.getItem(PREFIX + storageKey);
    if (raw) saved = JSON.parse(raw);
  } catch (_) {
    saved = {};
  }
  const selected = {};
  for (const n of names) {
    selected[n] = saved[n] !== false;
  }
  return selected;
}

export function persistLegendSelection(storageKey, params) {
  try {
    if (!params?.selected || typeof params.selected !== "object") return;
    sessionStorage.setItem(PREFIX + storageKey, JSON.stringify(params.selected));
  } catch (_) {
    /* ignore quota / private mode */
  }
}
