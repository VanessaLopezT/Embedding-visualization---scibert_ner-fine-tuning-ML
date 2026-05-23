# Checklist de verificación visual/funcional

Usar después de cada fase del refactor web.

**Refactor 2026-06-08:** CSS extraído a `web/css/app.css` + `responsive.css`; JS de orquestación en `web/js/app.js`; módulos en `api/`, `charts/`, `ui/`, `utils/`; resize ECharts centralizado en `web/js/ui/chartResize.js`.

## Vistas de gráfica
- [ ] Artículo · Vista Original (puntos, leyenda, toolbox, hover → panel texto)
- [ ] Artículo · Vista Frecuencia (escala artículo/global, expansión de entidad)
- [ ] Artículo · Vista Relaciones (filtros, slider exigencia, aristas curvas)
- [ ] Workspace · General (agregado, expansión radial)
- [ ] Workspace · Relaciones (filtros, exigencia, leyenda categorías)

## Layout y resize
- [ ] Divisor panel gráfica/texto 30%–80%
- [ ] Redimensionar ventana del navegador
- [ ] Zoom navegador 90% / 110%
- [ ] Barra de progreso visible/oculta no deforma gráfica

## Responsive
- [ ] Desktop (>1024px)
- [ ] Tablet (~768px)
- [ ] Móvil (<768px, paneles apilados)

## Flujos de app
- [ ] Cambio modelo tech / cmt / ambos
- [ ] Modo artículos vs workspaces
- [ ] Carga de artículo, modales, selección en dropdowns
- [ ] Sin errores en consola del navegador

## ECharts (no regresión)
- [ ] dataZoom rueda X/Y independiente
- [ ] tooltips y colores de series/aristas iguales
- [ ] export PNG fondo #fafafa
