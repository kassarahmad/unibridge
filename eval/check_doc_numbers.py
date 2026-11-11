"""Check that numbers written in the documentation come from result files.

1. Text between RESULTS markers must equal what eval/render_results.py would generate now (no hand edits, no stale tables).
2. Every decimal number OUTSIDE those blocks in the checked documents must match (at its printed precision) a
   numeric value found in eval/results/*.json (P14 documents) or eval/results/unibridge/*.json (UniBridge documents).

Usage:
    python eval/check_doc_numbers.py   (exit 1 on any mismatch)
"""

from __future__ import annotations

import json
import re
import sys

from common import RESULTS, ROOT
from render_results import blocks

DOCS = ["docs/REPORT.md", "docs/EVALUATION.md", "docs/DATA.md", "docs/DECISIONS.md", "docs/REPRODUCIBILITY.md"]
# PROCEDURE.md is not checked: its numbers are article numbers and amounts quoted from the call.
UB_DOCS = ["docs/REPORT_UNIBRIDGE.md", "docs/DATA_UNIBRIDGE.md"]
BLOCK_RE = re.compile(r"<!-- RESULTS:(\w+):START -->\n(.*?)\n<!-- RESULTS:\1:END -->", re.S)
NUM_RE = re.compile(r"(?<![\w.\-/])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+)( ?%)?(?![\w.])")
# Not data: section numbers in headings, software versions.
IGNORE_LINE_RE = re.compile(r"^\s*#|python 3\.\d+|python3\.\d+|uv python install|version 5\.0", re.IGNORECASE)


def result_values(folder=RESULTS) -> set[float]:
    values: set[float] = set()

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            values.add(float(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for path in folder.glob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return values


def main() -> int:
    expected = blocks()
    p14_values, ub_values = result_values(), result_values(RESULTS / "unibridge")
    problems = []
    for rel in DOCS + UB_DOCS:
        values = ub_values if rel in UB_DOCS else p14_values
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for name, content in BLOCK_RE.findall(text):
            if content != expected.get(name):
                problems.append(f"{rel}: block {name} is stale or hand-edited (re-run eval/render_results.py)")
        prose = "\n".join(ln for ln in BLOCK_RE.sub("", text).splitlines() if not IGNORE_LINE_RE.search(ln))
        for raw, pct in NUM_RE.findall(prose):
            num = raw.replace(",", "")
            decimals = len(num.split(".")[1]) if "." in num else 0
            target = float(num)
            candidates = [v * 100 for v in values] if pct else []
            candidates += list(values)
            if not any(abs(round(v, decimals) - target) < 10 ** (-decimals) / 2 + 1e-9 for v in candidates):
                problems.append(f"{rel}: number {raw}{pct} not found in the result files")
    for p in problems:
        print("MISMATCH", p)
    print(f"checked {len(DOCS + UB_DOCS)} documents: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
