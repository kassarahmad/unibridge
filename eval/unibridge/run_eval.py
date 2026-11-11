"""UniBridge retrieval evaluation on the frozen TEST split: B0 (BM25), S1 (dense), S2 (hybrid RRF).

Same metrics as P14 (eval/run_eval.py), reported overall, by query language (it/en/ar), by query source
(official FAQ / LLM translation / LLM paraphrase) and by language x source; ACL leakage for every UniBridge
role; paired randomization tests. Thresholds for insufficient_evidence come from the tuning-split
calibration (eval/results/unibridge/calibration.json).

Hypothesis tested (not assumed): BM25 fails on Arabic queries over Italian text.

Usage:
    python eval/unibridge/run_eval.py
Outputs: eval/results/unibridge/eval_<timestamp>.json, eval_<timestamp>_per_query.csv, eval_latest.json
"""

from __future__ import annotations

import csv
import json
import sys

from ub_common import CALIBRATION, RESULTS, load_qrels, principals, queries, search_service, timestamp, unibridge_settings, write_json

from freeze_test import test_hash, verify  # noqa: E402  (eval/ is on sys.path via ub_common)
from run_eval import visible  # noqa: E402  (independent restatement of the ACL rules, P14 oracle)

from p14_search.evaluation.metrics import paired_randomization_test
from p14_search.evaluation.runner import aggregate, hardware, run_queries, score

SYSTEMS = ("B0", "S1", "S2")


def acl_leakage(search, test, users) -> dict:
    docs = {r["passage_id"]: (r["access_level"], r["office"]) for r in search.store.query(
        "SELECT p.passage_id, d.access_level, d.office FROM passages p JOIN documents d ON d.document_id = p.document_id")}
    checks = leaks = 0
    for p in users.values():
        for q in test:
            for r in search.rank_all(q["query"], p, 10, SYSTEMS).values():
                for h in r.hits:
                    checks += 1
                    if not visible(p.level.value, p.offices, *docs[h.passage_id]):
                        leaks += 1
    return {"principals": len(users), "queries": len(test), "systems": len(SYSTEMS), "passages_checked": checks, "leaks": leaks}


def main() -> int:
    if not verify("unibridge"):
        raise SystemExit("test split changed since it was frozen (eval/freeze_test.py --dataset unibridge --verify)")
    if not CALIBRATION.exists():
        raise SystemExit("run eval/unibridge/calibrate.py first (thresholds are calibrated on the tuning split)")
    settings = unibridge_settings()
    search = search_service(settings=settings)
    users = principals(settings)
    test = queries("test")
    qrels = load_qrels()

    runs = run_queries(search, test, users, SYSTEMS)
    for by_qid in runs.values():
        for q in test:
            by_qid[q["qid"]].metrics = score(by_qid[q["qid"]], qrels[q["qid"]], q["type"] != "out_of_scope")

    def agg(subset: list[dict]) -> dict:
        return {s: aggregate(runs[s], subset) for s in SYSTEMS}

    langs = sorted({q["lang"] for q in test})
    sources = ("official_faq", "llm_translation", "llm_paraphrase")
    in_scope = [q for q in test if q["type"] != "out_of_scope"]
    by_lang = {lang: agg([q for q in test if q["lang"] == lang]) for lang in langs}
    by_source = {src: agg([q for q in test if q["source"] == src]) for src in sources}
    by_lang_source = {f"{lang}/{src}": agg([q for q in in_scope if q["lang"] == lang and q["source"] == src])
                      for lang in langs for src in sources if any(q["lang"] == lang and q["source"] == src for q in in_scope)}
    stats = {
        f"{a}_vs_{b}_{m}_{lang}": paired_randomization_test(
            [runs[a][q["qid"]].metrics[m] for q in in_scope if lang in ("all", q["lang"])],
            [runs[b][q["qid"]].metrics[m] for q in in_scope if lang in ("all", q["lang"])])
        for a, b in (("S2", "B0"), ("S1", "B0"), ("S2", "S1")) for m in ("ndcg@10", "recall@10") for lang in ("all", *langs)
    }
    # BM25 hypothesis: share of Arabic in-scope test queries for which BM25 returns no relevant passage in the top 10.
    bm25_ar = [q for q in in_scope if q["lang"] == "ar"]
    hypothesis = {
        "statement": "BM25 fails on Arabic queries over Italian text",
        "n_arabic_in_scope_test": len(bm25_ar),
        "B0_no_relevant_in_top10_share_ar": round(sum(1 for q in bm25_ar if runs["B0"][q["qid"]].metrics["mrr@10"] == 0) / max(len(bm25_ar), 1), 4),
        "B0_empty_result_share_ar": round(sum(1 for q in bm25_ar if not runs["B0"][q["qid"]].ranked) / max(len(bm25_ar), 1), 4),
        "ndcg@10_ar": {s: by_lang["ar"][s]["ndcg@10"] for s in SYSTEMS},
        "ndcg@10_it": {s: by_lang["it"][s]["ndcg@10"] for s in SYSTEMS},
    }
    leakage = acl_leakage(search, test, users)
    cal = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    ts = timestamp()
    report = {
        "generated_at": ts,
        "test_split_sha256": test_hash("unibridge")[0],
        "calibration": {"ie_min_dense": cal["ie_min_dense"], "ie_min_bm25": cal["ie_min_bm25"], "source": "eval/results/unibridge/calibration.json"},
        "versions": search.versions().model_dump(),
        "hardware": hardware(),
        "n_test_queries": len(test),
        "n_by_lang": {lang: sum(1 for q in test if q["lang"] == lang) for lang in langs},
        "overall": agg(test),
        "by_lang": by_lang,
        "by_source": by_source,
        "by_lang_source": by_lang_source,
        "hypothesis_bm25_arabic": hypothesis,
        "randomization_tests": stats,
        "acl_leakage": leakage,
    }
    write_json(RESULTS / f"eval_{ts}.json", report)
    write_json(RESULTS / "eval_latest.json", report)
    with open(RESULTS / f"eval_{ts}_per_query.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cols = ["recall@10", "precision@10", "mrr@10", "ndcg@10", "correct_source@3"]
        w.writerow(["qid", "lang", "source", "type", "system", "insufficient_evidence", *cols, "top_dense", "top_bm25", "top3_passages"])
        for q in test:
            for s in SYSTEMS:
                r = runs[s][q["qid"]]
                w.writerow([q["qid"], q["lang"], q["source"], q["type"], s, r.insufficient_evidence, *[r.metrics.get(c) for c in cols],
                            r.top_dense and round(r.top_dense, 4), r.top_bm25 and round(r.top_bm25, 4), " ".join(r.ranked[:3])])
    keys = ("ndcg@10", "recall@10", "mrr@10", "correct_source@3", "abstention_correctness", "false_abstention_rate")
    print("overall", json.dumps({s: {m: report["overall"][s][m] for m in keys} for s in SYSTEMS}, indent=1))
    print("by_lang ndcg@10", json.dumps({lang: {s: by_lang[lang][s]["ndcg@10"] for s in SYSTEMS} for lang in langs}))
    print("by_lang recall@10", json.dumps({lang: {s: by_lang[lang][s]["recall@10"] for s in SYSTEMS} for lang in langs}))
    print("hypothesis", json.dumps(hypothesis))
    print("leakage", leakage)
    print(f"-> eval/results/unibridge/eval_{ts}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
