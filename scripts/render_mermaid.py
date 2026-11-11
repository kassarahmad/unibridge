"""Render Mermaid diagrams (docs/diagrams/*.mmd) to PNG in docs/images/ with the locally installed Microsoft Edge.

Mermaid is loaded from the jsDelivr CDN (pinned version), so rendering needs network access. A diagram with a
syntax error makes the script fail, which also checks the .mmd files.

Usage:
    python scripts/render_mermaid.py [glob, default: ub-*.mmd]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "diagrams"
OUT = ROOT / "docs" / "images"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
PAGE = f"""<!doctype html><html><head><meta charset="utf-8"><script src="{MERMAID}"></script></head>
<body style="margin:0;background:#fff"><div id="d"></div></body></html>"""


def main() -> int:
    from playwright.sync_api import sync_playwright

    pattern = sys.argv[1] if len(sys.argv) > 1 else "ub-*.mmd"
    files = sorted(SRC.glob(pattern))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(device_scale_factor=2)
        page.set_content(PAGE)
        page.wait_for_function("window.mermaid !== undefined")
        page.evaluate("mermaid.initialize({startOnLoad: false, theme: 'default', flowchart: {htmlLabels: true}})")
        for f in files:
            code = f.read_text(encoding="utf-8")
            svg = page.evaluate(f"async () => (await mermaid.render('g', {json.dumps(code)})).svg")
            page.evaluate("svg => { document.getElementById('d').innerHTML = svg; }", svg)
            out = OUT / f"{f.stem}.png"
            page.locator("#d svg").screenshot(path=str(out))
            print(f"wrote {out.relative_to(ROOT).as_posix()}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
