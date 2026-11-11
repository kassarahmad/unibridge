"""Render docs/bpmn/scholarship.bpmn (BPMN 2.0 with diagram interchange) to docs/images/scholarship_bpmn.png.

Uses the bpmn-js viewer (pinned version, loaded from unpkg) in the locally installed Microsoft Edge, so the picture is
drawn from the same file that WoPeD / Camunda Modeler / bpmn.io would open.

Usage:
    python scripts/render_bpmn.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "bpmn" / "scholarship.bpmn"
OUT = ROOT / "docs" / "images" / "scholarship_bpmn.png"
VIEWER = "https://unpkg.com/bpmn-js@17.11.1/dist/bpmn-viewer.production.min.js"


def main() -> int:
    from playwright.sync_api import sync_playwright

    xml = SRC.read_text(encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 2400, "height": 1400}, device_scale_factor=2)
        page.set_content(f'<!doctype html><html><head><script src="{VIEWER}"></script></head>'
                         '<body style="margin:0;background:#fff"><div id="c" style="width:2400px;height:1400px"></div></body></html>')
        page.wait_for_function("window.BpmnJS !== undefined")
        page.evaluate(f"""async () => {{
            const v = new BpmnJS({{container: '#c', textRenderer: {{defaultStyle: {{fontSize: 9, lineHeight: 1.1}}, externalStyle: {{fontSize: 9, lineHeight: 1.1}}}}}});
            await v.importXML({json.dumps(xml)});
            v.get('canvas').zoom('fit-viewport', 'auto');
        }}""")
        page.wait_for_timeout(500)
        box = page.evaluate("""() => {
            const b = document.querySelector('#c .viewport').getBoundingClientRect();
            return {x: Math.max(b.x - 10, 0), y: Math.max(b.y - 10, 0), width: b.width + 20, height: b.height + 20};
        }""")
        page.screenshot(path=str(OUT), clip=box)
        browser.close()
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
