/**
 * chartResize.js
 * Resize centralizado para instancias ECharts (sin modificar opciones visuales).
 */

const chartGetters = new Set();
let windowResizeBound = false;

/**
 * Programa resize en dos frames (mismo patrón que el template original).
 * @param {import('echarts').ECharts | null | undefined} chart
 */
export function scheduleChartResize(chart) {
  if (!chart || typeof chart.resize !== "function") return;
  requestAnimationFrame(() => {
    chart.resize();
    requestAnimationFrame(() => chart.resize());
  });
}

/**
 * Registra un getter de chart para resize en window (un solo listener global).
 * @param {() => import('echarts').ECharts | null | undefined} getChart
 */
export function registerChartWindowResize(getChart) {
  if (typeof getChart !== "function") return;
  chartGetters.add(getChart);
  if (windowResizeBound || typeof window === "undefined") return;
  windowResizeBound = true;
  window.addEventListener("resize", () => {
    chartGetters.forEach((getter) => scheduleChartResize(getter()));
  });
}

/**
 * Observa cambios de tamaño del host del canvas (panel, media queries, resizer).
 * @param {Element | null | undefined} hostEl
 * @param {() => import('echarts').ECharts | null | undefined} getChart
 * @returns {() => void} cleanup
 */
export function attachChartResizeObserver(hostEl, getChart) {
  if (!hostEl || typeof ResizeObserver === "undefined") {
    return () => {};
  }
  const observer = new ResizeObserver(() => {
    scheduleChartResize(getChart());
  });
  observer.observe(hostEl);
  return () => observer.disconnect();
}

/**
 * Inicializa resize global + observer para la app principal.
 * @param {object} options
 * @param {() => import('echarts').ECharts | null | undefined} options.getChart
 * @param {Element | null | undefined} [options.hostEl]
 * @returns {() => void}
 */
export function initChartResizeManager({ getChart, hostEl }) {
  registerChartWindowResize(getChart);
  return attachChartResizeObserver(hostEl, getChart);
}
