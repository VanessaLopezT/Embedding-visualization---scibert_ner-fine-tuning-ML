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
// Claves normalizadas: sin espacios alrededor de "/", minúsculas, sin espacios dobles.
// getColorForLabel normaliza el input de la misma manera antes de buscar.
const CMT_COLORS_NORMALIZED = {
  "pathology/tumor type":              "#e63946",  // rojo
  "species/subject":                   "#2a9d8f",  // verde azulado
  "biomarkers and molecules":          "#e9c46a",  // ámbar
  "histopathology and grade":          "#f4a261",  // naranja
  "staging and prognosis":             "#a8dadc",  // celeste
  "diagnostic imaging and techniques": "#457b9d",  // azul acero
  "treatment":                         "#6a4c93",  // morado
  "comparative oncology":              "#80b918",  // verde lima
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
  // CMT con claves en el formato original para la leyenda
  "Pathology/Tumor Type":              "#e63946",
  "Species/Subject":                   "#2a9d8f",
  "Biomarkers and Molecules":          "#e9c46a",
  "Histopathology and Grade":          "#f4a261",
  "Staging and Prognosis":             "#a8dadc",
  "Diagnostic Imaging and Techniques": "#457b9d",
  "Treatment":                         "#6a4c93",
  "Comparative Oncology":              "#80b918",
};
