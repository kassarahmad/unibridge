"""Evaluate the scholarship guide on the 15 fictional scenarios of procedure_scenarios.json.

For each scenario the guide's verdict, rule outcomes, checklist (item -> status), net marking and next steps are
compared with the expected values written from the ERDIS call. A scenario is correct only if all five match.
Also checks that every rule citation resolves to an indexed passage of the call.

Usage:
    python eval/unibridge/eval_procedure.py   -> eval/results/unibridge/procedure_eval.json
"""

from __future__ import annotations

import json
import sys

from ub_common import RESULTS, ROOT, timestamp, unibridge_settings, write_json

from p14_search.indexing.store import Store
from p14_search.models import ProcedureRequest
from p14_search.procedure.guide import ScholarshipGuide

FIELDS = ("verdict", "rules", "checklist", "marking", "next")


def observed(r) -> dict:
    return {
        "verdict": r.verdict,
        "rules": {x.id: x.outcome for x in r.rules},
        "checklist": {c.id: c.status for c in r.checklist},
        "marking": r.status.marking,
        "next": [s.id for s in r.status.next],
    }


def main() -> int:
    guide = ScholarshipGuide(Store(unibridge_settings().sqlite_path))
    scenarios = json.loads((ROOT / "eval" / "unibridge" / "procedure_scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    per, field_ok = [], {f: 0 for f in FIELDS}
    for s in scenarios:
        got = observed(guide.guide(ProcedureRequest(**s["input"]), f"eval-{s['id']}"))
        exp = s["expected"]
        match = {f: (sorted(got[f]) == sorted(exp[f]) if f in ("marking", "next") else got[f] == exp[f]) for f in FIELDS}
        for f in FIELDS:
            field_ok[f] += match[f]
        diffs = {f: {"expected": exp[f], "got": got[f]} for f in FIELDS if not match[f]}
        per.append({"id": s["id"], "correct": all(match.values()), "diffs": diffs})
    n = len(scenarios)
    unresolved = sorted(k for k, v in guide.passages.items() if v is None)
    report = {
        "generated_at": timestamp(),
        "n_scenarios": n,
        "scenarios_fully_correct": sum(p["correct"] for p in per),
        "accuracy": round(sum(p["correct"] for p in per) / n, 4),
        "field_accuracy": {f: round(v / n, 4) for f, v in field_ok.items()},
        "rule_citations": len(guide.passages), "rule_citations_unresolved": unresolved,
        "per_scenario": per,
    }
    write_json(RESULTS / "procedure_eval.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "per_scenario"}, indent=1))
    for p in per:
        if not p["correct"]:
            print(p["id"], json.dumps(p["diffs"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
