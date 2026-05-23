"""One-off helper: extract inline CSS/JS from templates/index.html."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "templates" / "index.html"
APP_CSS = ROOT / "web" / "css" / "app.css"
APP_JS = ROOT / "web" / "js" / "app.js"

STATIC_IMPORTS = [
    ("{% static 'js/dataLoader.js' %}?v=20260405", "./dataLoader.js?v=20260405"),
    ("{% static 'js/tsneChart.js' %}?v=20260606_axis_auto", "./tsneChart.js?v=20260606_axis_auto"),
    ("{% static 'js/tsneChartFrequency.js' %}?v=20260606_axis_auto", "./tsneChartFrequency.js?v=20260606_axis_auto"),
    ("{% static 'js/tsneChartRelations.js' %}?v=20260606_axis_auto", "./tsneChartRelations.js?v=20260606_axis_auto"),
    (
        "{% static 'js/workspaceAggregateChart.js' %}?v=20260502axis_scale",
        "./workspaceAggregateChart.js?v=20260502axis_scale",
    ),
    (
        "{% static 'js/workspaceRelationsChart.js' %}?v=20260607_article_xy_overlay",
        "./workspaceRelationsChart.js?v=20260607_article_xy_overlay",
    ),
    ("{% static 'js/textPanel.js' %}?v=20260604occ_key", "./textPanel.js?v=20260604occ_key"),
    ("{% static 'js/workspaceApi.js' %}?v=20260401", "./workspaceApi.js?v=20260401"),
    ("{% static 'js/viewDataCache.js' %}?v=20260603article_rel", "./viewDataCache.js?v=20260603article_rel"),
]


def main() -> None:
    html = HTML.read_text(encoding="utf-8")
    styles = re.findall(r"<style>(.*?)</style>", html, re.DOTALL)
    if len(styles) < 2:
        raise SystemExit(f"Expected 2 style blocks, found {len(styles)}")
    app_css = "\n\n".join(s.strip() for s in styles) + "\n"
    APP_CSS.write_text(app_css, encoding="utf-8")

    m = re.search(r'<script type="module">\s*(.*?)\s*</script>\s*</body>', html, re.DOTALL)
    if not m:
        raise SystemExit("script module block not found")
    body = m.group(1)
    for old, new in STATIC_IMPORTS:
        body = body.replace(f'"{old}"', f'"{new}"')
    APP_JS.write_text(body + "\n", encoding="utf-8")
    print(f"Wrote {APP_CSS} ({len(app_css.splitlines())} lines)")
    print(f"Wrote {APP_JS} ({len(body.splitlines())} lines)")


if __name__ == "__main__":
    main()
