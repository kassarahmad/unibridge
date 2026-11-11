"""Evaluate the handoff office choice (rule table config/handoff_offices.json) on the frozen TEST split.

Ground truth for an in-scope query = office of its first target document (scholarship: ERDIS documents;
student_office / international: UNICAM documents). Out-of-scope queries should get no office. No LLM is used
(the office choice is deterministic); the tie-break uses the office of the best retrieved passage, as the API.

Usage:
    python eval/unibridge/eval_handoff.py   -> eval/results/unibridge/handoff_eval.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from ub_common import RESULTS, principals, queries, search_service, timestamp, unibridge_settings, write_json

from p14_search.handoff.service import HandoffService


def main() -> int:
    settings = unibridge_settings()
    search = search_service(settings=settings)
    users = principals(settings)
    office_of = {r["document_id"]: r["office"] for r in search.store.query("SELECT document_id, office FROM documents")}
    service = HandoffService(llm=None)
    rows = []
    for q in queries("test"):
        hits = search.rank_all(q["query"], users[q["principal"]], 5, ("S2",))["S2"].hits
        docs = search.hydrate(hits, users[q["principal"]])
        top = docs[0].metadata.office if docs else None
        chosen, _ = service.choose_office(q["query"], top)
        expected = office_of[q["targets"][0]["document_id"]] if q["targets"] else None
        rows.append({"qid": q["qid"], "lang": q["lang"], "type": q["type"], "expected": expected, "chosen": chosen,
                     "correct": chosen == expected})
    ins = [r for r in rows if r["expected"]]
    oos = [r for r in rows if not r["expected"]]
    acc = lambda xs: round(sum(r["correct"] for r in xs) / len(xs), 4) if xs else None  # noqa: E731
    report = {
        "generated_at": timestamp(),
        "n": len(rows),
        "in_scope_office_accuracy": acc(ins),
        "in_scope_no_office_share": round(sum(1 for r in ins if r["chosen"] is None) / max(len(ins), 1), 4),
        "out_of_scope_no_draft": acc(oos),
        "by_lang": {lang: acc([r for r in ins if r["lang"] == lang]) for lang in ("it", "en", "ar")},
        "confusion": {f"{e}->{c}": n for (e, c), n in sorted(Counter((r["expected"], r["chosen"]) for r in rows).items(), key=str)},
        "per_query": rows,
    }
    write_json(RESULTS / "handoff_eval.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "per_query"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
