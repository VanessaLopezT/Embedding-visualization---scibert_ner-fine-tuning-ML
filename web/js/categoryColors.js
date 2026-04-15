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
