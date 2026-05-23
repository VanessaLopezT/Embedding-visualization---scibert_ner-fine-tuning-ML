/**
 * Curvatura por par (determinística): separa aristas que comparten casi la misma cuerda.
 * crossBoost > 0 empuja un poco más el arco para aristas tech↔cmt (vista combinada).
 */
export function relationLineCurveness(sourceKey, targetKey, crossBoost = 0) {
  const a = String(sourceKey || "");
  const b = String(targetKey || "");
  const x = a <= b ? a : b;
  const y = a <= b ? b : a;
  let h = 2166136261 >>> 0;
  for (let i = 0; i < x.length; i += 1) {
    h = Math.imul(h ^ x.charCodeAt(i), 16777619) >>> 0;
  }
  for (let i = 0; i < y.length; i += 1) {
    h = Math.imul(h ^ y.charCodeAt(i), 16777619) >>> 0;
  }
  const u = (h % 1001) / 1000;
  let v = (u - 0.5) * 0.38;
  const boost = Number(crossBoost) || 0;
  if (boost > 0) {
    const sign = u >= 0.5 ? 1 : -1;
    v += sign * 0.06 * Math.min(1.5, boost);
  }
  const out = Math.max(-0.28, Math.min(0.28, v));
  return Number.isFinite(out) ? out : 0.1;
}
