/**
 * categoryColors.js
 * Paleta de colores por categoría de entidad.
 * Cubre tanto el modelo Tech (SciBERT) como el modelo CMT (PubMedBERT).
 *
 * IMPORTANTE: getColorForLabel normaliza el label antes de buscar,
 * eliminando espacios alrededor de "/" y colapsando espacios múltiples.
 * Así cubre todas las variantes que puede emitir el tokenizador.
 */

// ── Modelo Tech (ML / Technology) ──────────────────────────────────────
const TECH_COLORS = {
  "APPLICATION":  "#d63384",
  "ARCHITECTURE": "#6f42c1",
  "DATASET":      "#fd7e14",
  "TECHNOLOGY":   "#20c997",
  "MODEL":        "#0d6efd",
  "METRIC":       "#198754",
  "TECHNIQUE":    "#ffc107",
};

// ── Modelo CMT (Canine Mammary Tumor / PubMedBERT) ─────────────────────
// Categorías de la documentación (8): Pathologic Features, Etiology, Diagnosis, Type_sample,
// Statistical Descriptor, System_Organ, Treatment, Comparative Oncology
// Categorías que el modelo está emitiendo actualmente: Prognosis, staging, organ systems
const CMT_COLORS_NORMALIZED = {
  // Categorías de la documentación (por si las arreglan)
  "pathologic features":    "#e63946",  // rojo
  "etiology":               "#2a9d8f",  // verde azulado
  "diagnosis":              "#fd7e14",  // naranja
  "type_sample":            "#ffc107",  // amarillo
  "statistical descriptor": "#a855f7",  // morado claro
  "system_organ":           "#06b6d4",  // cyan
  "treatment":              "#d63384",  // rosa/magenta
  "comparative oncology":   "#84cc16",  // verde lima
  // Categorías que el modelo está emitiendo actualmente
  "prognosis":              "#6f42c1",  // morado
  "staging":                "#20c997",  // verde menta
  "organ systems":          "#0d6efd",  // azul
};

/**
 * Normaliza un label para búsqueda robusta:
 * - minúsculas
 * - elimina espacios alrededor de "/"
 * - colapsa espacios múltiples
 */
function _normalize(label) {
  return String(label || "")
    .toLowerCase()
    .replace(/\s*\/\s*/g, "/")   // "Pathology / Tumor Type" → "pathology/tumor type"
    .replace(/\s+/g, " ")        // espacios múltiples → uno
    .trim();
}

function _parseHex(hex) {
  const h = String(hex || "").replace("#", "").trim();
  if (h.length === 3) {
    return [
      parseInt(h[0] + h[0], 16),
      parseInt(h[1] + h[1], 16),
      parseInt(h[2] + h[2], 16),
    ];
  }
  if (h.length === 6) {
    return [
      parseInt(h.slice(0, 2), 16),
      parseInt(h.slice(2, 4), 16),
      parseInt(h.slice(4, 6), 16),
    ];
  }
  return [136, 136, 136];
}

function _rgbToHex(r, g, b) {
  const clamp = (n) => Math.max(0, Math.min(255, Math.round(n)));
  const x = (n) => clamp(n).toString(16).padStart(2, "0");
  return `#${x(r)}${x(g)}${x(b)}`;
}

function _blendHex(a, b, t) {
  const A = _parseHex(a);
  const B = _parseHex(b);
  const u = Math.max(0, Math.min(1, t));
  return _rgbToHex(
    A[0] + (B[0] - A[0]) * u,
    A[1] + (B[1] - A[1]) * u,
    A[2] + (B[2] - A[2]) * u
  );
}

/**
 * Devuelve el color para una etiqueta dada.
 * Compatible con labels tech (mayúsculas) y CMT (con espacios y barras).
 */
export function getColorForLabel(label) {
  if (!label) return "#888888";

  // 1. Búsqueda directa en Tech (mayúsculas exactas)
  if (TECH_COLORS[label]) return TECH_COLORS[label];

  // 2. Búsqueda tech case-insensitive
  const upper = String(label).toUpperCase();
  if (TECH_COLORS[upper]) return TECH_COLORS[upper];

  // 3. Búsqueda CMT con normalización
  const norm = _normalize(label);
  if (CMT_COLORS_NORMALIZED[norm]) return CMT_COLORS_NORMALIZED[norm];

  // 4. Búsqueda parcial CMT (por si el modelo emite variantes truncadas)
  for (const [key, color] of Object.entries(CMT_COLORS_NORMALIZED)) {
    if (norm.includes(key) || key.includes(norm)) return color;
  }

  return "#888888";
}

/**
 * Vista "Ambos": mismo círculo para todos; Tech y coincidencia ambos modelos
 * usan el color fuerte de categoría; solo PatVet (cmt) se apaga mezclando
 * hacia gris claro para menos saturación.
 */
export function ambosOriginFillColor(label, origin) {
  const base = getColorForLabel(label);
  const o = String(origin || "joint").toLowerCase();
  if (o === "cmt") {
    return _blendHex(base, "#eceff1", 0.58);
  }
  return base;
}

/**
 * Color del icono de leyenda en vista "Ambos": mayoría de orígenes entre puntos de la serie.
 */
export function ambosSeriesLegendFill(label, originSamples) {
  const list = Array.isArray(originSamples) ? originSamples : [];
  const counts = { tech: 0, cmt: 0, joint: 0 };
  for (const raw of list) {
    const o = String(raw || "joint").toLowerCase();
    if (o === "tech") counts.tech += 1;
    else if (o === "cmt") counts.cmt += 1;
    else counts.joint += 1;
  }
  let pick = "joint";
  let best = -1;
  for (const k of ["tech", "cmt", "joint"]) {
    if (counts[k] > best) {
      best = counts[k];
      pick = k;
    }
  }
  return ambosOriginFillColor(label, pick);
}

// Export del mapa completo para la leyenda del gráfico
export const CATEGORY_COLORS = {
  ...TECH_COLORS,
  // CMT categorías de la documentación
  "Pathologic Features":  "#e63946",
  "Etiology":             "#2a9d8f",
  "Diagnosis":            "#fd7e14",
  "Type_sample":          "#ffc107",
  "Statistical Descriptor": "#a855f7",
  "System_Organ":         "#06b6d4",
  "Treatment":            "#d63384",
  "Comparative Oncology": "#84cc16",
  // CMT categorías que el modelo está emitiendo actualmente
  "Prognosis":            "#6f42c1",
  "Staging":              "#20c997",
  "Organ systems":        "#0d6efd",
};
