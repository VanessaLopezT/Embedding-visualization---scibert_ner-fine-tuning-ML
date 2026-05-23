/**
 * panelResizer.js
 * Divisor redimensionable entre panel de gráfica y panel de texto.
 */

/**
 * @param {object} options
 * @param {HTMLElement} options.resizer
 * @param {HTMLElement} options.chartPanel
 * @param {HTMLElement} options.textPanel
 * @param {HTMLElement} options.container
 * @param {() => void} [options.onResize]
 */
export function initPanelResizer({ resizer, chartPanel, textPanel, container, onResize }) {
  if (!resizer || !chartPanel || !textPanel || !container) return;

  let isResizing = false;

  resizer.addEventListener("mousedown", () => {
    isResizing = true;
  });

  document.addEventListener("mousemove", (e) => {
    if (!isResizing) return;
    const rect = container.getBoundingClientRect();
    const newChartWidth = ((e.clientX - rect.left) / container.offsetWidth) * 100;
    if (newChartWidth > 30 && newChartWidth < 80) {
      chartPanel.style.flex = String(newChartWidth);
      textPanel.style.width = `${100 - newChartWidth}%`;
      if (typeof onResize === "function") onResize();
    }
  });

  document.addEventListener("mouseup", () => {
    isResizing = false;
  });
}
