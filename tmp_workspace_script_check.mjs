
  import { loadTSNEData }                                from "{% static 'js/dataLoader.js' %}?v=20260315";
  import { initTSNEChart }                               from "{% static 'js/tsneChart.js' %}?v=20260327";
  import { initTSNEFrequencyChart, resetFrequencyExpansion } from "{% static 'js/tsneChartFrequency.js' %}?v=20260327";
  import { initTSNERelationsChart, resetRelationsSelection } from "{% static 'js/tsneChartRelations.js' %}?v=20260327";
  import { initWorkspaceAggregateChart }                 from "{% static 'js/workspaceAggregateChart.js' %}?v=20260401";
  import { initWorkspaceRelationsChart, resetWorkspaceRelationsSelection } from "{% static 'js/workspaceRelationsChart.js' %}?v=20260401";
  import { renderText }                                  from "{% static 'js/textPanel.js' %}?v=20260324";
  import { listWorkspaces, getWorkspace, createWorkspace, updateWorkspaceArticles, processWorkspace, deleteWorkspace } from "{% static 'js/workspaceApi.js' %}?v=20260401";

  // ── URLs de API ──────────────────────────────────────────────────────
  const config = {
    exampleUrl:      (model) => `/api/example/tsne?model=${model}`,
    listUrl:         "/api/articles",
    uploadUrl:       "/api/articles/upload",
    workspaceAggregateUrl: (id, model) => `/api/workspaces/${id}/aggregate?model=${model}`,
    workspaceRelationsUrl: (id, model) => `/api/workspaces/${id}/relations?model=${model}`,
    tsneUrl:         (id, model) => `/api/articles/${id}/tsne?model=${model}`,
    metaUrl:         (id)        => `/api/articles/${id}/meta`,
    cleanedTextUrl:  (id)        => `/api/articles/${id}/cleaned-text`,
  };

  // ── Estado global ─────────────────────────────────────────────────────
  let currentChart   = null;
  let isUploadInProgress = false;
  let chartViewMode      = "standard";
  let baseChartViewMode  = "standard";
  let previousChartViewMode = "standard";
  let frequencyScaleMode = "article";
  let globalFrequencyReferenceMax = 1;
  let currentModelKey = "tech";   // modelo activo
  let currentScopeMode = "articles";
  let currentWorkspaceId = "";
  let currentWorkspaceChartMode = "aggregate";
  let workspaceRelationsFilterMode = "all";
  let currentWorkspaceVisibleEdgeCount = 0;
  let workspaceListState = [];
  let currentWorkspaceData = null;

  const panelState = {
    source: "example",
    articleId: null,
    mode: "entities",
    data: [],
    totalParagraphs: null,
    articleTitle: null,
    cleanedText: "",
  };

  // ── Elementos DOM ─────────────────────────────────────────────────────
  const textContentEl          = document.getElementById("text-content");
  const entitiesSummary        = document.getElementById("entities-summary");
  const mainContainer          = document.getElementById("container");
  const dataSourceEl           = document.getElementById("data-source");
  const dataSourceLabelEl      = document.getElementById("data-source-label");
  const btnEntitiesOnly        = document.getElementById("btn-entities-only");
  const btnAllParagraphs       = document.getElementById("btn-all-paragraphs");
  const entitiesCountEl        = document.getElementById("entities-count");
  const chartOriginalBtn       = document.getElementById("chart-original-btn");
  const chartFrequencyBtn      = document.getElementById("chart-frequency-btn");
  const chartRelationsBtn      = document.getElementById("chart-relations-btn");
  const chartHelp              = document.getElementById("chart-help");
  const chartHelpTooltip       = document.getElementById("chart-help-tooltip");
  const chartRelationsHelp     = document.getElementById("chart-relations-help");
  const frequencyScaleControls = document.getElementById("frequency-scale-controls");
  const frequencyScaleSelect   = document.getElementById("frequency-scale-select");
  const workspaceRelationsFilterControls = document.getElementById("workspace-relations-filter-controls");
  const workspaceRelationsFilterSelect = document.getElementById("workspace-relations-filter-select");
  const workspaceChartSummary = document.getElementById("workspace-chart-summary");
  const progressContainer      = document.getElementById("progress-container");
  const progressBar            = document.getElementById("progress-bar");
  const progressLabel          = document.getElementById("progress-label");
  const entitiesInfo           = document.getElementById("entities-info");
  const progressClose          = document.getElementById("progress-close");
  const modelSelect            = document.getElementById("model-select");
  const chartPanelEl           = document.getElementById("chart-panel");
  const textPanelEl            = document.getElementById("text-panel");
  const resizerEl              = document.getElementById("resizer");
  const articleSelect          = document.getElementById("article-select");
  const modeArticlesBtn        = document.getElementById("mode-articles-btn");
  const modeWorkspacesBtn      = document.getElementById("mode-workspaces-btn");
  const articleControls        = document.getElementById("article-controls");
  const workspaceControls      = document.getElementById("workspace-controls");
  const workspaceSelect        = document.getElementById("workspace-select");
  const workspaceArticleSelect = document.getElementById("workspace-article-select");
  const workspaceArticleControls = document.getElementById("workspace-article-controls");
  const workspaceViewArticlesBtn = document.getElementById("workspace-view-articles-btn");
  const workspaceViewGlobalBtn   = document.getElementById("workspace-view-global-btn");
  const workspaceNewBtn        = document.getElementById("workspace-new-btn");
  const workspaceManageBtn     = document.getElementById("workspace-manage-btn");
  const workspaceProcessBtn    = document.getElementById("workspace-process-btn");
  const uploadArticleBtn       = document.getElementById("upload-article-btn");
  const fileInput              = document.getElementById("file-input");
  const loadingIndicator       = document.getElementById("loading");

  const workspaceCreateModal   = document.getElementById("modal-workspace-create");
  const workspaceNameInput     = document.getElementById("workspace-name-input");
  const workspaceDescriptionInput = document.getElementById("workspace-description-input");
  const workspaceCreateCancelBtn = document.getElementById("workspace-create-cancel-btn");
  const workspaceCreateSaveBtn   = document.getElementById("workspace-create-save-btn");

  const workspaceManageModal   = document.getElementById("modal-workspace-manage");
  const workspaceManageTitle   = document.getElementById("workspace-manage-title");
  const workspaceCurrentArticlesEl = document.getElementById("workspace-current-articles");
  const workspaceAvailableArticlesEl = document.getElementById("workspace-available-articles");
  const workspaceManageDeleteBtn = document.getElementById("workspace-manage-delete-btn");
  const workspaceManageCloseBtn = document.getElementById("workspace-manage-close-btn");

  // ── Utilidades ────────────────────────────────────────────────────────
  function extractBodyParagraphs(cleanedText) {
    const text = String(cleanedText || "").trim();
    if (!text) return [];
    return text
      .split(/\r?\n\s*\r?\n/)
      .map(p => p.trim())
      .filter(Boolean)
      .flatMap(p => {
        if (!/^TITLE:\s*/i.test(p)) return [p];
        const withoutTitle = p.replace(/^TITLE:\s*[^\r\n]*\s*/i, "").trim();
        return withoutTitle ? [withoutTitle] : [];
      });
  }

  function getParagraphsWithEntitiesCount(data, cleanedText = "") {
    if (!Array.isArray(data) || !data.length) return 0;

    const paragraphs = extractBodyParagraphs(cleanedText);
    if (!paragraphs.length) {
      return new Set(
        data
          .filter(p => !String(p.sentence_text || "").trim().match(/^TITLE:\s*/i))
          .map(p => p.sentence_id)
      ).size;
    }

    const normalize = (value) => String(value || "")
      .toLowerCase()
      .replace(/[“”"']/g, "")
      .replace(/\s*([.,:;!?()[\]{}])\s*/g, "$1")
      .replace(/\s*-\s*/g, "-")
      .replace(/\s*\/\s*/g, "/")
      .replace(/\s+/g, " ")
      .trim();
    const normalizedParagraphs = paragraphs.map(normalize).filter(Boolean);
    const entityTexts = Array.from(new Set(
      data
        .map(p => normalize(p?.entity || ""))
        .filter(text => text && !/^title:\s*/i.test(text))
    ));

    let count = 0;
    normalizedParagraphs.forEach(paragraph => {
      const hasEntity = entityTexts.some(entity => paragraph.includes(entity));
      if (hasEntity) count += 1;
    });
    return count;
  }

  function getMaxEntityFrequency(data) {
    if (!Array.isArray(data) || !data.length) return 1;
    const counts = new Map();
    data.forEach(p => {
      const key = String(p?.entity || "").trim().toLowerCase().replace(/\s+/g, " ");
      if (!key) return;
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    let max = 1;
    counts.forEach(v => { if (v > max) max = v; });
    return max;
  }

  // ── Renderizado ───────────────────────────────────────────────────────
  function updateDataSourceLabel(source, data, totalParagraphs = null, cleanedText = "") {
    const entities = Array.isArray(data) ? data.length : 0;
    const paragraphsWithEntities = getParagraphsWithEntitiesCount(data, cleanedText);
    const isEmpty = entities === 0;
    const baseColor = isEmpty ? "#c44d56" : "#999";

    dataSourceEl.style.color = baseColor;
    if (entitiesCountEl) {
      entitiesCountEl.textContent = `Entidades: ${entities}`;
      entitiesCountEl.style.color = baseColor;
    }
    if (btnEntitiesOnly) {
      btnEntitiesOnly.textContent = `P\u00E1rrafos con entidades: ${paragraphsWithEntities}`;
      btnEntitiesOnly.classList.toggle("active", panelState.mode === "entities");
    }
    if (btnAllParagraphs) {
      const totalText = typeof totalParagraphs === "number" ? totalParagraphs : "-";
      btnAllParagraphs.textContent = `P\u00E1rrafos totales: ${totalText}`;
      btnAllParagraphs.classList.toggle("active", panelState.mode === "all");
      btnAllParagraphs.disabled = source !== "article";
    }
    if (dataSourceLabelEl) {
      dataSourceLabelEl.textContent = source === "article"
        ? "Datos del art\u00EDculo"
        : "Datos de ejemplo";
    }
  }

  function renderCurrentTextPanel() {
    renderText(panelState.data, textContentEl, panelState.articleTitle, {
      mode: panelState.mode,
      cleanedText: panelState.cleanedText,
    });
    updateDataSourceLabel(panelState.source, panelState.data, panelState.totalParagraphs, panelState.cleanedText);
  }

  function setWorkspaceLayout(isWorkspaceMode) {
    if (textPanelEl) textPanelEl.style.display = isWorkspaceMode ? "none" : "";
    if (resizerEl) resizerEl.style.display = isWorkspaceMode ? "none" : "";
    if (chartPanelEl) chartPanelEl.style.flex = isWorkspaceMode ? "1 1 100%" : "";
    if (workspaceChartSummary) workspaceChartSummary.style.display = isWorkspaceMode ? "block" : "none";
    if (currentChart) requestAnimationFrame(() => currentChart.resize());
  }

  function setWorkspaceChartSummary(text = "") {
    if (!workspaceChartSummary) return;
    workspaceChartSummary.textContent = text;
    workspaceChartSummary.style.display = currentScopeMode === "workspaces" && text ? "block" : "none";
  }

  function renderEmptyArticleState(message = "Selecciona un articulo para visualizar sus resultados.") {
    const chartDom = document.getElementById("tsne-chart");
    if (currentChart) currentChart.dispose();
    currentChart = echarts.init(chartDom);
    currentChart.clear();

    panelState.source = "article";
    panelState.articleId = null;
    panelState.mode = "entities";
    panelState.data = [];
    panelState.totalParagraphs = 0;
    panelState.articleTitle = null;
    panelState.cleanedText = "";

    textContentEl.innerHTML = `
      <div style="padding:24px 18px; text-align:center; color:#666;">
        <div style="font-size:15px; font-weight:600; margin-bottom:8px;">Sin seleccion</div>
        <div style="font-size:13px; line-height:1.6;">${message}</div>
      </div>
    `;
    updateDataSourceLabel("article", [], 0, "");
    if (entitiesSummary) entitiesSummary.textContent = "Entidades: 0";
    setWorkspaceChartSummary("");
  }

  function renderEmptyWorkspaceState(message = "Selecciona un workspace para explorar sus articulos.") {
    const chartDom = document.getElementById("tsne-chart");
    if (currentChart) currentChart.dispose();
    currentChart = echarts.init(chartDom);
    currentChart.clear();

    panelState.source = "article";
    panelState.articleId = null;
    panelState.mode = "entities";
    panelState.data = [];
    panelState.totalParagraphs = 0;
    panelState.articleTitle = "Workspace";
    panelState.cleanedText = "";

    textContentEl.innerHTML = `
      <div style="padding:24px 18px; text-align:center; color:#666;">
        <div style="font-size:15px; font-weight:600; margin-bottom:8px;">Sin workspace seleccionado</div>
        <div style="font-size:13px; line-height:1.6;">${message}</div>
      </div>
    `;
    const chartContainer = document.getElementById("tsne-chart");
    if (chartContainer) {
      chartContainer.innerHTML = `
        <div style="height:100%; display:flex; align-items:center; justify-content:center; padding:24px; color:#666; text-align:center;">
          <div>
            <div style="font-size:16px; font-weight:600; margin-bottom:10px;">Workspace sin contenido visible</div>
            <div style="font-size:13px; line-height:1.7;">${message}</div>
          </div>
        </div>
      `;
    }
    updateDataSourceLabel("article", [], 0, "");
    if (entitiesSummary) entitiesSummary.textContent = "Entidades: 0";
    setWorkspaceChartSummary("");
  }

  async function loadWorkspaceAggregate(workspaceId, modelKey = currentModelKey) {
    const response = await fetch(config.workspaceAggregateUrl(workspaceId, modelKey));
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "No se pudo cargar la grafica del workspace");
    }

    const points = Array.isArray(payload.points) ? payload.points : [];
    if (!points.length) {
      renderEmptyWorkspaceState(
        payload.total_article_count > 0
          ? "Este workspace aun no tiene articulos procesados para el modelo seleccionado."
          : "Este workspace aun no tiene articulos."
      );
      return;
    }

    const chartDom = document.getElementById("tsne-chart");
    if (currentChart) currentChart.dispose();
    currentChart = echarts.init(chartDom);
    resetFrequencyExpansion();
    resetRelationsSelection();
    initWorkspaceAggregateChart(currentChart, payload);

    panelState.source = "article";
    panelState.articleId = null;
    panelState.mode = "entities";
    panelState.data = [];
    panelState.totalParagraphs = 0;
    panelState.articleTitle = payload.workspace_name || "Workspace";
    panelState.cleanedText = "";
    textContentEl.innerHTML = "";
    currentWorkspaceVisibleEdgeCount = 0;
    if (entitiesSummary) entitiesSummary.textContent = `Entidades: ${points.length}`;
    setWorkspaceChartSummary(
      `Entidades: ${Number(payload.unique_entity_count || points.length || 0)} · Ocurrencias: ${Number(payload.total_entity_occurrences || 0)}`
    );
  }

  async function loadWorkspaceRelations(workspaceId, modelKey = currentModelKey) {
    const response = await fetch(config.workspaceRelationsUrl(workspaceId, modelKey));
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "No se pudo cargar la grafica de relaciones del workspace");
    }

    const nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
    if (!nodes.length) {
      renderEmptyWorkspaceState(
        payload.total_article_count > 0
          ? "Este workspace aun no tiene articulos procesados para el modelo seleccionado."
          : "Este workspace aun no tiene articulos."
      );
      return;
    }

    const chartDom = document.getElementById("tsne-chart");
    if (currentChart) currentChart.dispose();
    currentChart = echarts.init(chartDom);
    resetFrequencyExpansion();
    resetRelationsSelection();
    initWorkspaceRelationsChart(currentChart, payload, {
      filterMode: workspaceRelationsFilterMode,
      onRenderSummary: ({ visibleEdgeCount }) => {
        currentWorkspaceVisibleEdgeCount = Number(visibleEdgeCount || 0);
        setWorkspaceChartSummary(
          `Entidades: ${Number(payload.unique_entity_count || nodes.length || 0)} · Ocurrencias: ${Number(payload.total_entity_occurrences || 0)} · Relaciones: ${Number(visibleEdgeCount || 0)}`
        );
      },
    });

    panelState.source = "article";
    panelState.articleId = null;
    panelState.mode = "entities";
    panelState.data = [];
    panelState.totalParagraphs = 0;
    panelState.articleTitle = payload.workspace_name || "Workspace";
    panelState.cleanedText = "";
    textContentEl.innerHTML = "";
    if (entitiesSummary) entitiesSummary.textContent = `Entidades: ${nodes.length}`;
    setWorkspaceChartSummary(
      `Entidades: ${Number(payload.unique_entity_count || nodes.length || 0)} · Ocurrencias: ${Number(payload.total_entity_occurrences || 0)}`
    );
  }

  function updateChartModeButton() {
    if (currentScopeMode === "workspaces") {
      if (chartOriginalBtn) {
        chartOriginalBtn.hidden = false;
        chartOriginalBtn.textContent = "Vista: General";
        chartOriginalBtn.classList.toggle("active", currentWorkspaceChartMode === "aggregate");
      }
      if (chartFrequencyBtn) {
        chartFrequencyBtn.hidden = true;
        chartFrequencyBtn.classList.remove("active");
      }
      if (chartRelationsBtn) {
        chartRelationsBtn.hidden = false;
        chartRelationsBtn.textContent = "Vista: Relaciones";
        chartRelationsBtn.classList.toggle("active", currentWorkspaceChartMode === "relations");
      }
      if (chartHelp) {
        chartHelp.hidden = false;
      }
      if (chartHelpTooltip) {
        chartHelpTooltip.innerHTML = `
          <strong>&iquest;Qu&eacute; ves aqu&iacute;?</strong><br>
          Cada punto agrupa una entidad detectada en los art&iacute;culos procesados del workspace.<br><br>
          <strong>Vista: General</strong> resume la presencia global de conceptos del workspace para el modelo seleccionado.<br><br>
          <strong>Vista: Relaciones</strong> muestra afinidad contextual entre esas entidades agregadas, usando solo resultados ya procesados del workspace.<br><br>
          Usa el <strong>selector de modelo</strong> para cambiar el enfoque sin volver a procesar lo que ya existe.
        `;
      }
      if (chartRelationsHelp) {
        chartRelationsHelp.hidden = currentWorkspaceChartMode !== "relations";
      }
      if (frequencyScaleControls) {
        frequencyScaleControls.style.display = "none";
      }
      if (workspaceRelationsFilterControls) {
        workspaceRelationsFilterControls.style.display = currentWorkspaceChartMode === "relations" ? "flex" : "none";
      }
      return;
    }

    if (chartOriginalBtn) {
      chartOriginalBtn.hidden = false;
      chartOriginalBtn.textContent = "Vista: Original";
      chartOriginalBtn.classList.toggle("active", chartViewMode === "standard");
    }
    if (chartFrequencyBtn) {
      chartFrequencyBtn.hidden = false;
      chartFrequencyBtn.classList.toggle("active", chartViewMode === "frequency");
    }
    if (chartRelationsBtn) {
      chartRelationsBtn.hidden = false;
      chartRelationsBtn.classList.toggle("active", chartViewMode === "relations");
      chartRelationsBtn.textContent = "Vista: Relaciones";
    }
    if (chartHelp) {
      chartHelp.hidden = false;
    }
    if (chartHelpTooltip) {
      chartHelpTooltip.innerHTML = `
        <strong>&iquest;Qu&eacute; ves aqu&iacute;?</strong><br>
        Cada punto es una entidad detectada en el texto.<br><br>
        <strong>Dimensi&oacute;n 1 y Dimensi&oacute;n 2</strong> son una proyecci&oacute;n 2D para visualizar
        cercan&iacute;a sem&aacute;ntica: puntos cercanos aparecen en contextos parecidos.<br><br>
        Si cambias a <strong>Vista: Frecuencia</strong>, cada palabra aparece una sola vez
        y el tama&ntilde;o del punto representa cu&aacute;ntas veces se detect&oacute;.<br><br>
        En <strong>Vista: Relaciones</strong>, cada nodo agrupa una entidad y su tama&ntilde;o
        crece seg&uacute;n cu&aacute;ntas veces se repite; las l&iacute;neas muestran afinidad contextual
        entre entidades del art&iacute;culo.<br><br>
        Usa el <strong>selector de modelo</strong> (arriba izquierda) para cambiar entre
        el modelo ML/Tech y el modelo de oncolog&iacute;a veterinaria (CMT).
      `;
    }
    if (chartRelationsHelp) {
      chartRelationsHelp.hidden = chartViewMode !== "relations";
    }
    if (frequencyScaleControls) {
      frequencyScaleControls.style.display = chartViewMode === "frequency" ? "flex" : "none";
    }
    if (workspaceRelationsFilterControls) {
      workspaceRelationsFilterControls.style.display = "none";
    }
  }

  function switchChartView(nextMode) {
    const resolvedMode = chartViewMode === nextMode ? previousChartViewMode : nextMode;
    if (!resolvedMode || resolvedMode === chartViewMode) return;

    previousChartViewMode = chartViewMode;
    chartViewMode = resolvedMode;

    if (chartViewMode === "standard" || chartViewMode === "frequency") {
      baseChartViewMode = chartViewMode;
    }
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
    } catch (_) { return null; }
  }

  function renderChartByMode(data, axisRange = null) {
    if (!currentChart) return;
    if (chartViewMode === "relations") {
      resetFrequencyExpansion();
      initTSNERelationsChart(currentChart, data, axisRange, {
        minEntityFrequency: 1,
        topEntities: 40,
        minSentenceCooccurrence: 1,
        scoreThreshold: 0.16,
        maxEdges: 120,
        isolateSelection: false,
      });
      return;
    }
    if (chartViewMode === "frequency") {
      resetRelationsSelection();
      if (frequencyScaleMode === "global") {
        globalFrequencyReferenceMax = Math.max(globalFrequencyReferenceMax, getMaxEntityFrequency(data));
      }
      initTSNEFrequencyChart(currentChart, data, axisRange, {
        scaleMode: frequencyScaleMode,
        globalReferenceMax: Math.max(2, globalFrequencyReferenceMax),
      });
      return;
    }
    resetRelationsSelection();
    initTSNEChart(currentChart, data, axisRange);
  }

  // ── Progreso ──────────────────────────────────────────────────────────
  function showProgress(label = "Procesando...") {
    progressContainer.style.display = "block";
    if (mainContainer) mainContainer.style.marginTop = "112px";
    progressBar.style.width = "10%";
    progressLabel.textContent = label;
    if (currentChart) requestAnimationFrame(() => currentChart.resize());
  }

  function hideProgress() {
    progressContainer.style.display = "none";
    if (mainContainer) mainContainer.style.marginTop = "70px";
    progressBar.style.width = "0%";
    progressLabel.textContent = "";
    if (entitiesInfo) entitiesInfo.textContent = "";
    if (currentChart) requestAnimationFrame(() => currentChart.resize());
  }

  if (progressClose) progressClose.addEventListener("click", hideProgress);

  // ── Carga de datos ────────────────────────────────────────────────────
  // ── Estado del modal ──────────────────────────────────────────────────
  let _pendingModalArticleId = null;
  let _pendingModalModel     = null;

  const modalEl         = document.getElementById("modal-process-model");
  const modalMsg        = document.getElementById("modal-process-msg");
  const modalProcessBtn = document.getElementById("modal-process-btn");
  const modalCancelBtn  = document.getElementById("modal-cancel-btn");

  function showModelModal(articleId, modelKey, articleName) {
    _pendingModalArticleId = articleId;
    _pendingModalModel     = modelKey;
    const modelLabel = modelSelect.options[modelSelect.selectedIndex]?.text || modelKey;
    modalMsg.textContent = `El artículo "${articleName || articleId}" aún no fue procesado con el modelo "${modelLabel}". ¿Deseas procesarlo ahora?`;
    modalEl.style.display = "flex";
  }

  if (modalCancelBtn) {
    modalCancelBtn.addEventListener("click", () => {
      if (modalEl) modalEl.style.display = "none";
      _pendingModalArticleId = null;
      _pendingModalModel     = null;
    });
  }

  if (modalProcessBtn) {
    modalProcessBtn.addEventListener("click", async () => {
      if (modalEl) modalEl.style.display = "none";
      if (!_pendingModalArticleId || !_pendingModalModel) return;
      await reprocessArticleWithModel(_pendingModalArticleId, _pendingModalModel);
      _pendingModalArticleId = null;
      _pendingModalModel     = null;
    });
  }

  async function reprocessArticleWithModel(articleId, modelKey) {
    // Buscar el archivo original del artículo y re-enviarlo al backend
    // con el nuevo modelo. Para esto usamos el endpoint de re-proceso.
    showProgress(`Procesando con modelo ${modelKey}...`);
    isUploadInProgress = true;
    try {
      const resp = await fetch(`/api/articles/${articleId}/reprocess`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelKey }),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.error || "Error al reprocesar");
      await pollArticleStatus(articleId, result.article?.original_name || articleId);
    } catch (err) {
      isUploadInProgress = false;
      hideProgress();
      alert("Error al reprocesar: " + err.message);
    }
  }

  async function loadAndRenderData(source, articleId = null, modelKey = currentModelKey) {
    try {
      let data, totalParagraphs = null, articleTitle = null, cleanedText = "";

      if (source === "article" && articleId) {
        const response = await fetch(config.tsneUrl(articleId, modelKey));
        if (!response.ok) {
          // Sin datos para este modelo → mostrar modal
          let artName = articleId;
          try {
            const metaR = await fetch(config.metaUrl(articleId));
            if (metaR.ok) { const m = await metaR.json(); artName = m?.article?.original_name || articleId; }
          } catch (_) {}
          showModelModal(articleId, modelKey, artName);
          return;
        }
        const result = await response.json();
        data = result.data;

        try {
          const [metaResp, cleanedResp] = await Promise.all([
            fetch(config.metaUrl(articleId)),
            fetch(config.cleanedTextUrl(articleId)),
          ]);
          if (metaResp.ok) {
            const meta = await metaResp.json();
            if (meta?.progress?.total) totalParagraphs = meta.progress.total;
            if (meta?.title)           articleTitle    = meta.title;
          }
          if (cleanedResp.ok) {
            const payload = await cleanedResp.json();
            if (payload?.text) {
              cleanedText    = payload.text;
              totalParagraphs = extractBodyParagraphs(cleanedText).length;
            }
          }
        } catch (_) {}

      } else {
        const result = await loadTSNEData(config.exampleUrl(modelKey));
        data = result.data;
        totalParagraphs = getParagraphsWithEntitiesCount(data);
      }

      const chartDom = document.getElementById("tsne-chart");
      if (currentChart) currentChart.dispose();
      currentChart = echarts.init(chartDom);

      resetFrequencyExpansion();
      resetRelationsSelection();
      renderChartByMode(data);

      panelState.source          = source;
      panelState.articleId       = articleId;
      panelState.mode            = "entities";
      panelState.data            = Array.isArray(data) ? data : [];
      panelState.totalParagraphs = totalParagraphs;
      panelState.articleTitle    = articleTitle;
      panelState.cleanedText     = cleanedText;

      renderCurrentTextPanel();
      if (entitiesSummary) entitiesSummary.textContent = `Entidades: ${panelState.data.length}`;

    } catch (error) {
      console.error("Error cargando datos:", error);
      alert("Error al cargar datos: " + error.message);
    }
  }

  async function refreshArticleList(selectedId = null) {
    try {
      const resp = await fetch(config.listUrl);
      if (!resp.ok) return "";
      const result = await resp.json();
      const select = document.getElementById("article-select");
      const current = selectedId || select.value;
      select.innerHTML = "";
      if (!Array.isArray(result.articles) || !result.articles.length) {
        select.innerHTML = '<option value="">Aun no hay articulos cargados</option>';
        select.value = "";
        return "";
      }
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Seleccionar articulo";
      select.appendChild(placeholder);
      result.articles.forEach(article => {
        const opt = document.createElement("option");
        opt.value = article.id;
        opt.textContent = `${article.original_name} (${article.status})`;
        select.appendChild(opt);
      });
      if (current && result.articles.some(article => article.id === current)) {
        select.value = current;
      } else {
        select.value = "";
      }
      return select.value || "";
    } catch (error) {
      console.error("Error listando articulos:", error);
      return "";
    }
  }

  // ── Carga inicial ─────────────────────────────────────────────────────
  function getSelectedArticleIdForCurrentMode() {
    if (currentScopeMode === "workspaces") {
      return workspaceArticleSelect?.value || "";
    }
    return articleSelect?.value || "";
  }

  function updateWorkspaceButtonsState() {
    const hasWorkspace = Boolean(currentWorkspaceId);
    const hasArticles = Number(currentWorkspaceData?.article_count || 0) > 0;
    if (workspaceManageBtn) workspaceManageBtn.disabled = !hasWorkspace;
    if (workspaceProcessBtn) workspaceProcessBtn.disabled = !hasWorkspace || !hasArticles;
    if (uploadArticleBtn && currentScopeMode === "workspaces") {
      uploadArticleBtn.disabled = !hasWorkspace;
    }
    if (workspaceArticleControls) workspaceArticleControls.hidden = true;
  }

  function updateScopeControls() {
    const isWorkspaceMode = currentScopeMode === "workspaces";
    setWorkspaceLayout(isWorkspaceMode);
    modeArticlesBtn?.classList.toggle("active", !isWorkspaceMode);
    modeWorkspacesBtn?.classList.toggle("active", isWorkspaceMode);
    if (articleControls) articleControls.hidden = isWorkspaceMode;
    if (workspaceControls) workspaceControls.hidden = !isWorkspaceMode;
    if (workspaceNewBtn) workspaceNewBtn.hidden = !isWorkspaceMode;
    if (workspaceManageBtn) workspaceManageBtn.hidden = !isWorkspaceMode;
    if (workspaceProcessBtn) workspaceProcessBtn.hidden = !isWorkspaceMode;
    if (uploadArticleBtn) uploadArticleBtn.textContent = isWorkspaceMode ? "Agregar Articulos" : "Cargar Articulo";
    if (uploadArticleBtn) {
      uploadArticleBtn.disabled = isWorkspaceMode ? !currentWorkspaceId : false;
    }
    if (entitiesSummary) {
      entitiesSummary.style.display = isWorkspaceMode ? "none" : "";
    }
    updateWorkspaceButtonsState();
  }

  function renderWorkspaceArticleOptions(workspace) {
    if (!workspaceArticleSelect) return;
    const currentValue = workspaceArticleSelect.value;
    workspaceArticleSelect.innerHTML = '<option value="">Seleccionar articulo del workspace</option>';
    const articles = Array.isArray(workspace?.articles)
      ? workspace.articles.filter(article => article?.exists && article?.status === "processed")
      : [];
    articles.forEach(article => {
      if (!article?.exists) return;
      const option = document.createElement("option");
      option.value = article.id;
      option.textContent = article.original_name || article.id;
      workspaceArticleSelect.appendChild(option);
    });
    const exists = articles.some(article => article?.id === currentValue && article?.exists);
    if (exists) {
      workspaceArticleSelect.value = currentValue;
    } else if (articles.length === 1 && articles[0]?.exists) {
      workspaceArticleSelect.value = articles[0].id;
    } else {
      workspaceArticleSelect.value = "";
    }
  }

  async function refreshWorkspaceList(selectedId = "") {
    try {
      const result = await listWorkspaces();
      workspaceListState = Array.isArray(result.workspaces) ? result.workspaces : [];
      const previousValue = selectedId || currentWorkspaceId || workspaceSelect?.value || "";
      if (workspaceSelect) {
        workspaceSelect.innerHTML = '<option value="">Seleccionar workspace</option>';
        workspaceListState.forEach(workspace => {
          const option = document.createElement("option");
          option.value = workspace.id;
          option.textContent = `${workspace.name} (${workspace.article_count || 0})`;
          workspaceSelect.appendChild(option);
        });
        if (previousValue && workspaceListState.some(workspace => workspace.id === previousValue)) {
          workspaceSelect.value = previousValue;
          currentWorkspaceId = previousValue;
        } else {
          workspaceSelect.value = "";
          currentWorkspaceId = "";
        }
      }
      updateWorkspaceButtonsState();
    } catch (error) {
      console.error("Error cargando workspaces:", error);
    }
  }

  async function loadWorkspace(workspaceId) {
    if (!workspaceId) {
      currentWorkspaceId = "";
      currentWorkspaceData = null;
      renderWorkspaceArticleOptions(null);
      updateWorkspaceButtonsState();
      if (currentScopeMode === "workspaces") {
        renderEmptyWorkspaceState();
      }
      return;
    }
    try {
      const result = await getWorkspace(workspaceId);
      const workspace = result.workspace || null;
      currentWorkspaceId = workspaceId;
      currentWorkspaceData = workspace;
      renderWorkspaceArticleOptions(workspace);
      if (workspaceSelect) workspaceSelect.value = workspaceId;
      updateWorkspaceButtonsState();
      if (currentScopeMode !== "workspaces") return;
      if (currentWorkspaceChartMode === "relations") {
        await loadWorkspaceRelations(workspaceId, currentModelKey);
      } else {
        await loadWorkspaceAggregate(workspaceId, currentModelKey);
      }
    } catch (error) {
      console.error("Error cargando workspace:", error);
      alert("Error cargando workspace: " + error.message);
    }
  }

  function closeWorkspaceCreateModal() {
    if (workspaceCreateModal) workspaceCreateModal.style.display = "none";
    if (workspaceNameInput) workspaceNameInput.value = "";
    if (workspaceDescriptionInput) workspaceDescriptionInput.value = "";
  }

  function closeWorkspaceManageModal() {
    if (workspaceManageModal) workspaceManageModal.style.display = "none";
  }

  function createWorkspaceArticleRow(article, actionLabel, actionHandler) {
    const row = document.createElement("div");
    row.style.display = "flex";
    row.style.alignItems = "center";
    row.style.justifyContent = "space-between";
    row.style.gap = "12px";
    row.style.padding = "10px 12px";
    row.style.border = "1px solid #e6e6e6";
    row.style.borderRadius = "8px";
    row.style.background = "#fafafa";

    const info = document.createElement("div");
    info.style.display = "flex";
    info.style.flexDirection = "column";
    info.style.gap = "4px";

    const title = document.createElement("span");
    title.textContent = article.original_name || article.id;
    title.style.fontSize = "13px";
    title.style.color = "#333";

    const meta = document.createElement("span");
    const modelState = article.models?.[currentModelKey] || "sin datos";
    meta.textContent = `Estado ${currentModelKey}: ${modelState}`;
    meta.style.fontSize = "11px";
    meta.style.color = "#777";

    info.appendChild(title);
    info.appendChild(meta);

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = actionLabel;
    button.style.padding = "6px 12px";
    button.style.border = "1px solid #d0d0d0";
    button.style.borderRadius = "6px";
    button.style.background = "#fff";
    button.style.cursor = "pointer";
    button.style.fontSize = "12px";
    button.addEventListener("click", actionHandler);

    row.appendChild(info);
    row.appendChild(button);
    return row;
  }

  async function renderWorkspaceManageModal() {
    if (!currentWorkspaceId) return;
    const result = await getWorkspace(currentWorkspaceId);
    const workspace = result.workspace || null;
    currentWorkspaceData = workspace;

    if (workspaceManageTitle) {
      workspaceManageTitle.textContent = `Gestionar Workspace: ${workspace?.name || currentWorkspaceId}`;
    }

    const currentArticles = Array.isArray(workspace?.articles) ? workspace.articles.filter(article => article?.exists) : [];
    const allArticlesResp = await fetch(config.listUrl);
    const allArticlesResult = allArticlesResp.ok ? await allArticlesResp.json() : { articles: [] };
    const allArticles = Array.isArray(allArticlesResult.articles) ? allArticlesResult.articles : [];
    const currentIds = new Set(currentArticles.map(article => article.id));
    const availableArticles = allArticles.filter(article => !currentIds.has(article.id));

    if (workspaceCurrentArticlesEl) {
      workspaceCurrentArticlesEl.innerHTML = "";
      if (!currentArticles.length) {
        workspaceCurrentArticlesEl.innerHTML = '<div style="font-size:12px; color:#777;">No hay articulos en este workspace.</div>';
      } else {
        currentArticles.forEach(article => {
          workspaceCurrentArticlesEl.appendChild(createWorkspaceArticleRow(article, "Quitar", async () => {
            await updateWorkspaceArticles(currentWorkspaceId, [article.id], "remove");
            await refreshWorkspaceList(currentWorkspaceId);
            await loadWorkspace(currentWorkspaceId);
            await renderWorkspaceManageModal();
          }));
        });
      }
    }

    if (workspaceAvailableArticlesEl) {
      workspaceAvailableArticlesEl.innerHTML = "";
      if (!availableArticles.length) {
        workspaceAvailableArticlesEl.innerHTML = '<div style="font-size:12px; color:#777;">No hay articulos disponibles para agregar.</div>';
      } else {
        availableArticles.forEach(article => {
          workspaceAvailableArticlesEl.appendChild(createWorkspaceArticleRow({ ...article, models: {} }, "Agregar", async () => {
            await updateWorkspaceArticles(currentWorkspaceId, [article.id], "add");
            await refreshWorkspaceList(currentWorkspaceId);
            await loadWorkspace(currentWorkspaceId);
            await renderWorkspaceManageModal();
          }));
        });
      }
    }
  }

  await refreshArticleList();
  await refreshWorkspaceList();
  updateScopeControls();
  renderEmptyArticleState();

  // ── Selector de modelo ────────────────────────────────────────────────
  modelSelect.addEventListener("change", async () => {
    currentModelKey = modelSelect.value;
    updateChartModeButton();
    if (currentScopeMode === "workspaces") {
      if (currentWorkspaceId) {
        await loadWorkspace(currentWorkspaceId);
      } else {
        renderEmptyWorkspaceState();
      }
      return;
    }
    const articleId  = articleSelect.value;
    if (!articleId) {
      renderEmptyArticleState();
      return;
    }
    await loadAndRenderData("article", articleId, currentModelKey);
  });

  // ── Selector de artículo ──────────────────────────────────────────────
  articleSelect.addEventListener("change", async (e) => {
    if (!isUploadInProgress) hideProgress();
    const value = e.target.value;
    if (!value) {
      renderEmptyArticleState();
      return;
    }
    await loadAndRenderData("article", value, currentModelKey);
  });

  modeArticlesBtn?.addEventListener("click", async () => {
    resetWorkspaceRelationsSelection();
    currentScopeMode = "articles";
    updateScopeControls();
    updateChartModeButton();
    const articleId = articleSelect?.value || "";
    if (!articleId) {
      renderEmptyArticleState();
      return;
    }
    await loadAndRenderData("article", articleId, currentModelKey);
  });

  modeWorkspacesBtn?.addEventListener("click", async () => {
    resetWorkspaceRelationsSelection();
    currentScopeMode = "workspaces";
    updateScopeControls();
    updateChartModeButton();
    await refreshWorkspaceList(currentWorkspaceId);
    if (currentWorkspaceId) {
      await loadWorkspace(currentWorkspaceId);
    } else {
      renderEmptyWorkspaceState();
    }
  });

  workspaceSelect?.addEventListener("change", async (e) => {
    currentWorkspaceId = e.target.value || "";
    if (!currentWorkspaceId) {
      renderEmptyWorkspaceState();
      return;
    }
    await loadWorkspace(currentWorkspaceId);
  });

  workspaceArticleSelect?.addEventListener("change", async (e) => {
    const articleId = e.target.value || "";
    if (!articleId) return;
    await loadAndRenderData("article", articleId, currentModelKey);
  });

  workspaceViewArticlesBtn?.addEventListener("click", async () => {
    currentWorkspaceChartMode = "aggregate";
    updateChartModeButton();
    if (currentWorkspaceId) await loadWorkspace(currentWorkspaceId);
  });

  workspaceNewBtn?.addEventListener("click", () => {
    if (workspaceCreateModal) workspaceCreateModal.style.display = "flex";
  });

  workspaceCreateCancelBtn?.addEventListener("click", closeWorkspaceCreateModal);

  workspaceCreateSaveBtn?.addEventListener("click", async () => {
    const name = String(workspaceNameInput?.value || "").trim();
    const description = String(workspaceDescriptionInput?.value || "").trim();
    if (!name) {
      alert("El workspace necesita un nombre.");
      return;
    }
    try {
      const result = await createWorkspace({ name, description });
      closeWorkspaceCreateModal();
      currentWorkspaceId = result.workspace?.id || "";
      await refreshWorkspaceList(currentWorkspaceId);
      updateScopeControls();
      await loadWorkspace(currentWorkspaceId);
    } catch (error) {
      alert("Error creando workspace: " + error.message);
    }
  });

  workspaceManageBtn?.addEventListener("click", async () => {
    if (!currentWorkspaceId) return;
    await renderWorkspaceManageModal();
    if (workspaceManageModal) workspaceManageModal.style.display = "flex";
  });

  workspaceManageDeleteBtn?.addEventListener("click", async () => {
    if (!currentWorkspaceId) return;
    const workspaceName = currentWorkspaceData?.name || currentWorkspaceId;
    const confirmed = window.confirm(`¿Eliminar el workspace "${workspaceName}"?`);
    if (!confirmed) return;

    try {
      await deleteWorkspace(currentWorkspaceId);
      closeWorkspaceManageModal();
      currentWorkspaceId = "";
      currentWorkspaceData = null;
      await refreshWorkspaceList();
      updateScopeControls();
      if (currentScopeMode === "workspaces") {
        renderEmptyWorkspaceState();
      }
    } catch (error) {
      alert("Error eliminando workspace: " + error.message);
    }
  });

  workspaceManageCloseBtn?.addEventListener("click", closeWorkspaceManageModal);

  workspaceProcessBtn?.addEventListener("click", async () => {
    if (!currentWorkspaceId) return;
    if (!currentWorkspaceData || !Array.isArray(currentWorkspaceData.articles) || !currentWorkspaceData.articles.length) {
      alert("Este workspace aun no tiene articulos. Agrega articulos primero.");
      return;
    }
    try {
      const result = await processWorkspace(currentWorkspaceId, currentModelKey);
      const enqueued = Array.isArray(result.enqueued_article_ids) ? result.enqueued_article_ids.length : 0;
      const skipped = Array.isArray(result.skipped) ? result.skipped.length : 0;
      if (enqueued === 0 && skipped === 0) {
        alert("No hubo articulos para procesar en este workspace.");
        return;
      }
      await refreshWorkspaceList(currentWorkspaceId);
      await loadWorkspace(currentWorkspaceId);
      alert(`Workspace enviado a procesamiento en ${currentModelKey}: ${enqueued} encolados, ${skipped} omitidos.`);
    } catch (error) {
      alert("Error procesando workspace: " + error.message);
    }
  });


  // ── Toggle modo texto ─────────────────────────────────────────────────
  btnEntitiesOnly?.addEventListener("click", () => {
    panelState.mode = "entities";
    renderCurrentTextPanel();
  });

  btnAllParagraphs?.addEventListener("click", () => {
    if (panelState.source !== "article") return;
    panelState.mode = "all";
    renderCurrentTextPanel();
  });

  // ── Toggle modo gráfica ───────────────────────────────────────────────
  chartOriginalBtn?.addEventListener("click", () => {
    if (currentScopeMode === "workspaces") {
      resetWorkspaceRelationsSelection();
      currentWorkspaceChartMode = "aggregate";
      updateChartModeButton();
      if (currentWorkspaceId) {
        loadWorkspace(currentWorkspaceId);
      } else {
        renderEmptyWorkspaceState();
      }
      return;
    }

    const axisRange = getCurrentAxisRange(currentChart);
    switchChartView("standard");
    updateChartModeButton();
    if (currentChart && Array.isArray(panelState.data)) {
      resetFrequencyExpansion();
      resetRelationsSelection();
      renderChartByMode(panelState.data, axisRange);
    }
  });
  chartFrequencyBtn?.addEventListener("click", () => {
    if (currentScopeMode === "workspaces") return;

    const axisRange = getCurrentAxisRange(currentChart);
    switchChartView("frequency");
    updateChartModeButton();
    if (currentChart && Array.isArray(panelState.data)) {
      resetFrequencyExpansion();
      resetRelationsSelection();
      renderChartByMode(panelState.data, axisRange);
    }
  });
  updateChartModeButton();

  chartRelationsBtn?.addEventListener("click", () => {
    if (currentScopeMode === "workspaces") {
      resetWorkspaceRelationsSelection();
      currentWorkspaceChartMode = "relations";
      updateChartModeButton();
      if (currentWorkspaceId) {
        loadWorkspace(currentWorkspaceId);
      } else {
        renderEmptyWorkspaceState();
      }
      return;
    }

    const axisRange = getCurrentAxisRange(currentChart);
    switchChartView("relations");
    if (chartViewMode !== "relations") resetRelationsSelection();
    updateChartModeButton();
    if (currentChart && Array.isArray(panelState.data)) {
      renderChartByMode(panelState.data, axisRange);
    }
  });

  frequencyScaleSelect?.addEventListener("change", () => {
    frequencyScaleMode = frequencyScaleSelect.value === "global" ? "global" : "article";
    if (chartViewMode !== "frequency" || !currentChart || !Array.isArray(panelState.data)) return;
    const axisRange = getCurrentAxisRange(currentChart);
    renderChartByMode(panelState.data, axisRange);
  });

  workspaceRelationsFilterSelect?.addEventListener("change", () => {
    workspaceRelationsFilterMode = workspaceRelationsFilterSelect.value || "medium-high";
    if (currentScopeMode !== "workspaces" || currentWorkspaceChartMode !== "relations") return;
    if (currentWorkspaceId) {
      loadWorkspace(currentWorkspaceId);
    }
  });

  // ── Resizer ───────────────────────────────────────────────────────────
  const resizer   = document.getElementById("resizer");
  const chartPanel = document.getElementById("chart-panel");
  const textPanel  = document.getElementById("text-panel");
  let isResizing  = false;

  resizer.addEventListener("mousedown", () => { isResizing = true; });
  document.addEventListener("mousemove", (e) => {
    if (!isResizing) return;
    const container = document.getElementById("container");
    const newChartWidth = ((e.clientX - container.getBoundingClientRect().left) / container.offsetWidth) * 100;
    if (newChartWidth > 30 && newChartWidth < 80) {
      chartPanel.style.flex = newChartWidth;
      textPanel.style.width = (100 - newChartWidth) + "%";
      if (currentChart) currentChart.resize();
    }
  });
  document.addEventListener("mouseup", () => { isResizing = false; });

  // ── Upload de artículo ────────────────────────────────────────────────
  const uploadBtn = uploadArticleBtn;

  uploadBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    if (currentScopeMode === "workspaces" && !currentWorkspaceId) {
      alert("Primero selecciona o crea un workspace antes de cargar articulos aqui.");
      fileInput.value = "";
      return;
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
    isUploadInProgress = true;
    uploadBtn.disabled = true;
    loadingIndicator.classList.add("active");
    loadingIndicator.textContent = "Procesando...";
    showProgress(files.length > 1 ? `En cola... 0/${files.length}` : "En cola...");

    const formData = new FormData();
    files.forEach(file => formData.append("file", file));
    formData.append("model", currentModelKey);   // enviar modelo seleccionado
    if (currentScopeMode === "workspaces" && currentWorkspaceId) {
      formData.append("workspace_id", currentWorkspaceId);
    }

    try {
      const response = await fetch(config.uploadUrl, { method: "POST", body: formData });
      const result   = await response.json();

      if (response.ok && result.article) {
        await refreshArticleList();
        if (currentScopeMode === "workspaces" && currentWorkspaceId) {
          await refreshWorkspaceList(currentWorkspaceId);
        }
        await pollArticleStatus(result.article.id, files[0].name);
      } else if (response.ok && Array.isArray(result.articles) && result.articles.length) {
        await refreshArticleList();
        if (currentScopeMode === "workspaces" && currentWorkspaceId) {
          await refreshWorkspaceList(currentWorkspaceId);
        }

        const outcomes = [];
        for (let index = 0; index < result.articles.length; index += 1) {
          const article = result.articles[index];
          const fileName = article?.original_name || `articulo ${index + 1}`;
          const status = await pollArticleStatus(article.id, fileName, {
            suppressSuccessAlert: true,
            progressPrefix: `Archivo ${index + 1}/${result.articles.length}`,
            keepLoadedOnSuccess: index !== result.articles.length - 1,
          });
          outcomes.push(status);
        }

        await refreshArticleList();
        if (currentScopeMode === "workspaces" && currentWorkspaceId) {
          await refreshWorkspaceList(currentWorkspaceId);
          await loadWorkspace(currentWorkspaceId);
        }
        isUploadInProgress = false;
        hideProgress();

        const successCount = outcomes.filter(status => status === "processed").length;
        const failedCount = outcomes.filter(status => status === "failed").length;
        const timeoutCount = outcomes.filter(status => status === "timeout").length;
        const rejectedCount = Array.isArray(result.rejected) ? result.rejected.length : 0;
        alert(`Carga multiple completada: ${successCount} procesados, ${failedCount} fallidos, ${timeoutCount} pendientes, ${rejectedCount} rechazados.`);
      } else {
        isUploadInProgress = false;
        hideProgress();
        alert(`Error: ${result.error || "No se pudo procesar el art\u00EDculo"}`);
      }
    } catch (error) {
      isUploadInProgress = false;
      hideProgress();
      alert("Error al procesar art\u00EDculo: " + error.message);
    } finally {
      uploadBtn.disabled = false;
      loadingIndicator.classList.remove("active");
      loadingIndicator.textContent = "";
      fileInput.value = "";
    }
  });

  // ── Polling de estado ─────────────────────────────────────────────────
  async function pollArticleStatus(articleId, fileName, options = {}) {
    const suppressSuccessAlert = Boolean(options.suppressSuccessAlert);
    const keepLoadedOnSuccess = Boolean(options.keepLoadedOnSuccess);
    const progressPrefix = options.progressPrefix ? `${options.progressPrefix} · ` : "";
    const stageToProgress = {
      queued: 10, processing: 30, ner: 60, tsne: 85, completed: 100, failed: 100,
    };
    let attempts = 0;

    while (attempts < 300) {
      attempts++;
      try {
        const resp   = await fetch(config.metaUrl(articleId));
        const result = await resp.json();
        const article  = result.article || {};
        const progress = result.progress || {};

        const stage   = article.stage || "processing";
        const percent = typeof progress.percent === "number"
          ? progress.percent
          : (stageToProgress[stage] || 50);

        progressBar.style.width = `${percent}%`;

        const stageLabel = {
          completed: "Completado", failed: "Fall\u00F3",
          queued: "En cola...", ner: "Extrayendo entidades (NER)...",
          tsne: "Generando t-SNE...",
        }[stage] || "Procesando...";

        const countPart = (typeof progress.processed === "number" && typeof progress.total === "number" && progress.total > 0)
          ? ` ${progress.processed}/${progress.total}` : "";
        const entsPart  = typeof progress.entities_extracted === "number"
          ? ` \u00B7 entidades ${progress.entities_extracted}` : "";

        progressLabel.textContent = `${progressPrefix}${stageLabel}${countPart}${entsPart}`;
        if (entitiesInfo) {
          entitiesInfo.textContent = (typeof progress.processed === "number" && progress.total > 0)
            ? `P\u00E1rrafos: ${progress.processed}/${progress.total}`
            : "";
        }
        if (entitiesSummary && typeof progress.entities_extracted === "number") {
          entitiesSummary.textContent = `Entidades: ${progress.entities_extracted}`;
        }

        if (article.status === "processed") {
          progressBar.style.width = "100%";
          progressLabel.textContent = `${progressPrefix}Completado`;
          await refreshArticleList(articleId);
          if (currentScopeMode === "workspaces" && currentWorkspaceId) {
            await refreshWorkspaceList(currentWorkspaceId);
            await loadWorkspace(currentWorkspaceId);
          } else if (articleSelect) {
            articleSelect.value = articleId;
          }
          if (!keepLoadedOnSuccess && !(currentScopeMode === "workspaces" && currentWorkspaceId)) {
            await loadAndRenderData("article", articleId, currentModelKey);
          }
          if (!suppressSuccessAlert) {
            isUploadInProgress = false;
            hideProgress();
            alert(`Art\u00EDculo procesado correctamente: ${fileName}`);
          }
          return "processed";
        }

        if (article.status === "failed") {
          if (currentScopeMode === "workspaces" && currentWorkspaceId) {
            await refreshWorkspaceList(currentWorkspaceId);
            await loadWorkspace(currentWorkspaceId);
          }
          if (!suppressSuccessAlert) {
            isUploadInProgress = false;
            hideProgress();
            alert(`Error al procesar: ${article.error || "Revisa la consola del servidor"}`);
          }
          return "failed";
        }

      } catch (error) {
        console.error("Error consultando estado:", error);
      }
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    if (!suppressSuccessAlert && isUploadInProgress) hideProgress();
    return "timeout";
  }
