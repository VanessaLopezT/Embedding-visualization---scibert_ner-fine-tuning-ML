"""Patch templates/index.html: remove inline CSS/JS after extraction."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "templates" / "index.html"

HEAD_END = """  <script src="https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js"></script>
</head>
"""

SCRIPT_TAG = """<script type="module" src="{% static 'js/app.js' %}?v=20260608"></script>
"""


def main() -> None:
    html = HTML.read_text(encoding="utf-8")
    # Remove inline style block(s) after echarts script, keep links
    html = re.sub(
        r"<script src=\"https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js\"></script>\s*"
        r"(?:<!--.*?-->\s*)?"
        r"<style[^>]*>.*?</style>\s*",
        HEAD_END,
        html,
        count=1,
        flags=re.DOTALL,
    )
    # Replace inline module script with external
    html = re.sub(
        r"<script type=\"module\">.*?</script>\s*(?=</body>)",
        SCRIPT_TAG + "\n",
        html,
        count=1,
        flags=re.DOTALL,
    )
    HTML.write_text(html, encoding="utf-8")
    lines = len(html.splitlines())
    print(f"Patched {HTML} ({lines} lines)")


if __name__ == "__main__":
    main()
