import { loadTSNEData } from "./dataLoader.js";
import { createTSNEChart } from "./tsneChart.js";
// Punto de entrada principal para inicializar la aplicación
async function init() { 
  const result = await loadTSNEData("/api/example/tsne");
  const data = result.data;
  const chartDom = document.getElementById("chart");
  createTSNEChart(chartDom, data);
}

init();
