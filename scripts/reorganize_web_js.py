"""Move web/js modules into api/, charts/, ui/, utils/ and fix imports."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "js"

MOVES = {
    "dataLoader.js": "api/dataLoader.js",
    "workspaceApi.js": "api/workspaceApi.js",
    "tsneChart.js": "charts/tsneChart.js",
    "tsneChartFrequency.js": "charts/tsneChartFrequency.js",
    "tsneChartRelations.js": "charts/tsneChartRelations.js",
    "workspaceAggregateChart.js": "charts/workspaceAggregateChart.js",
    "workspaceRelationsChart.js": "charts/workspaceRelationsChart.js",
    "textPanel.js": "ui/textPanel.js",
    "categoryColors.js": "utils/categoryColors.js",
    "chartAxisUtils.js": "utils/chartAxisUtils.js",
    "relationLineCurveness.js": "utils/relationLineCurveness.js",
    "viewDataCache.js": "utils/viewDataCache.js",
    "legendSelectionPersist.js": "utils/legendSelectionPersist.js",
}

IMPORT_MAP = {
    "./dataLoader.js": "./api/dataLoader.js",
    "./workspaceApi.js": "./api/workspaceApi.js",
    "./tsneChart.js": "./charts/tsneChart.js",
    "./tsneChartFrequency.js": "./charts/tsneChartFrequency.js",
    "./tsneChartRelations.js": "./charts/tsneChartRelations.js",
    "./workspaceAggregateChart.js": "./charts/workspaceAggregateChart.js",
    "./workspaceRelationsChart.js": "./charts/workspaceRelationsChart.js",
    "./textPanel.js": "./ui/textPanel.js",
    "./categoryColors.js": "./utils/categoryColors.js",
    "./chartAxisUtils.js": "./utils/chartAxisUtils.js",
    "./relationLineCurveness.js": "./utils/relationLineCurveness.js",
    "./viewDataCache.js": "./utils/viewDataCache.js",
    "./legendSelectionPersist.js": "./utils/legendSelectionPersist.js",
    "./ui/chartResize.js": "./ui/chartResize.js",
}

# Relative imports from charts/ and ui/
FROM_CHARTS = {
    "./categoryColors.js": "../utils/categoryColors.js",
    "./chartAxisUtils.js": "../utils/chartAxisUtils.js",
    "./relationLineCurveness.js": "../utils/relationLineCurveness.js",
    "./textPanel.js": "../ui/textPanel.js",
}
FROM_UI = {
    "./categoryColors.js": "../utils/categoryColors.js",
}


def patch_imports(content: str, rel_prefix: str) -> str:
    """rel_prefix: '' for app.js root, '../' for subdirs handled per file."""
    for old, new in IMPORT_MAP.items():
        # preserve ?v= query strings
        content = re.sub(
            re.escape(f'from "{old}') + r"(\?[^\"]*)?\"",
            lambda m, n=new: f'from "{n}{m.group(1) or ""}"',
            content,
        )
    return content


def patch_file_imports(path: Path, content: str) -> str:
    rel = path.relative_to(JS)
    parts = rel.parts
    if parts[0] == "charts":
        for old, new in FROM_CHARTS.items():
            content = re.sub(
                re.escape(f'from "{old}') + r"(\?[^\"]*)?\"",
                lambda m, n=new: f'from "{n}{m.group(1) or ""}"',
                content,
            )
    elif parts[0] == "ui" and path.name == "textPanel.js":
        for old, new in FROM_UI.items():
            content = re.sub(
                re.escape(f'from "{old}') + r"(\?[^\"]*)?\"",
                lambda m, n=new: f'from "{n}{m.group(1) or ""}"',
                content,
            )
    elif path.name == "app.js":
        content = patch_imports(content, "")
    return content


def main() -> None:
    for src_name, dest_rel in MOVES.items():
        src = JS / src_name
        dest = JS / dest_rel
        if not src.exists():
            print("skip missing", src)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = src.read_text(encoding="utf-8")
        dest.write_text(content, encoding="utf-8")
        if src.resolve() != dest.resolve():
            src.unlink()
        print("moved", src_name, "->", dest_rel)

    # chartResize already in ui/
    for path in list(JS.rglob("*.js")):
        if path.name == "main.js":
            continue
        text = path.read_text(encoding="utf-8")
        patched = patch_file_imports(path, text)
        if patched != text:
            path.write_text(patched, encoding="utf-8")
            print("patched imports", path.relative_to(JS))

    # Thin re-exports at legacy paths for external references
    SHIMS = {
        "dataLoader.js": "api/dataLoader.js",
        "workspaceApi.js": "api/workspaceApi.js",
        "tsneChart.js": "charts/tsneChart.js",
        "tsneChartFrequency.js": "charts/tsneChartFrequency.js",
        "tsneChartRelations.js": "charts/tsneChartRelations.js",
        "workspaceAggregateChart.js": "charts/workspaceAggregateChart.js",
        "workspaceRelationsChart.js": "charts/workspaceRelationsChart.js",
        "textPanel.js": "ui/textPanel.js",
        "categoryColors.js": "utils/categoryColors.js",
        "chartAxisUtils.js": "utils/chartAxisUtils.js",
        "relationLineCurveness.js": "utils/relationLineCurveness.js",
        "viewDataCache.js": "utils/viewDataCache.js",
    }
    for legacy, target in SHIMS.items():
        shim = JS / legacy
        if shim.exists():
            continue
        rel = "./" + target
        shim.write_text(
            f'export * from "{rel}";\n',
            encoding="utf-8",
        )
        print("shim", legacy)


if __name__ == "__main__":
    main()
