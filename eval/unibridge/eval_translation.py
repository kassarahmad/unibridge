"""UniBridge experiment S3: translate non-Italian questions into Italian with the LLM before retrieval.

Systems compared on the frozen TEST split (same queries, qrels and metrics as eval/unibridge/run_eval.py):
- S1   dense (multilingual-e5-small) on the original question
- S2   hybrid BM25 + dense (RRF) on the original question
- S3   S2 on the LLM Italian translation of the question (Italian questions are not translated: S3 = S2)
- S3f  RRF of S2(original) and S2(translation): what the answer service does (src/p14_search/answer/service.py)

Nothing is tuned on the test split: the translation prompt is the one of the answer service (fixed in phase 4),
temperature 0, response cache on disk; the insufficient-evidence thresholds are the tuning-split calibration of S2,
applied unchanged (S3f flags insufficient evidence only when both runs do, as the answer service).
Translations are LLM output: they are saved with llm_generated: true for human review.

Usage:
    python eval/unibridge/eval_translation.py
Outputs: eval/results/unibridge/translation_<timestamp>.json, translation_<timestamp>_per_query.csv,
         translation_latest.json, eval/review/unibridge_query_translations.csv
"""

from __future__ import annotations

import csv
import json
import sys

from ub_common import CALIBRATION, RESULTS, ROOT, load_qrels, principals, queries, search_service, timestamp, unibridge_settings, write_json

from freeze_test import test_hash, verify  # noqa: E402  (eval/ is on sys.path via ub_common)

from p14_search.answer.llm import LLMError, build_llm
from p14_search.answer.service import translate_query
from p14_search.evaluation.metrics import paired_randomization_test
from p14_search.evaluation.runner import K, QueryRun, aggregate, score
from p14_search.retrieval.retrievers import rrf_fuse

SYSTEMS = ("S1", "S2", "S3", "S3f")
REVIEW = ROOT / "eval" / "review" / "unibridge_query_translations.csv"


def main() -> int:
    if not verify("unibridge"):
        raise SystemExit("test split changed since it was frozen (eval/freeze_test.py --dataset unibridge --verify)")
    if not CALIBRATION.exists():
        raise SystemExit("run eval/unibridge/calibrate.py first (thresholds are calibrated on the tuning split)")
    settings = unibridge_settings()
    llm = build_llm(settings)
    if llm is None:
        raise SystemExit("S3 needs an LLM: set LLM_PROVIDER, LLM_MODEL and LLM_API_KEY in .env")
    try:
        llm.complete("Reply with: ok", "ok", 2, "probe")
    except LLMError as exc:
        raise SystemExit(f"LLM not usable: {exc} ({exc.__cause__.__class__.__name__ if exc.__cause__ else ''})")
    search = search_service(settings=settings)
    users = principals(settings)
    test = queries("test")
    qrels = load_qrels()
    usage_start = settings.llm_usage_log.stat().st_size if settings.llm_usage_log.exists() else 0

    runs: dict[str, dict[str, QueryRun]] = {s: {} for s in SYSTEMS}
    translations = {}
    for q in test:
        p = users[q["principal"]]
        first = search.rank_all(q["query"], p, K, ("S1", "S2"))
        s2 = first["S2"]
        for s in ("S1", "S2"):
            r = first[s]
            runs[s][q["qid"]] = QueryRun(q["qid"], s, [h.passage_id for h in r.hits], r.insufficient_evidence, r.top_bm25, r.top_dense)
        if q["lang"] == "it":
            s3, fused, both_ie = s2, s2.hits, s2.insufficient_evidence
        else:
            italian = translate_query(llm, q["query"]).text.strip()
            translations[q["qid"]] = italian
            s3 = search.rank_all(italian, p, K, ("S2",))["S2"]
            fused = rrf_fuse({"original": s2.hits, "italian": s3.hits}, K)
            both_ie = s2.insufficient_evidence and s3.insufficient_evidence
        runs["S3"][q["qid"]] = QueryRun(q["qid"], "S3", [h.passage_id for h in s3.hits], s3.insufficient_evidence, s3.top_bm25, s3.top_dense)
        runs["S3f"][q["qid"]] = QueryRun(q["qid"], "S3f", [h.passage_id for h in fused], both_ie, None, None)
    for by_qid in runs.values():
        for q in test:
            by_qid[q["qid"]].metrics = score(by_qid[q["qid"]], qrels[q["qid"]], q["type"] != "out_of_scope")

    def agg(subset: list[dict]) -> dict:
        return {s: aggregate(runs[s], subset) for s in SYSTEMS}

    langs = ("it", "en", "ar")
    in_scope = [q for q in test if q["type"] != "out_of_scope"]
    by_lang = {lang: agg([q for q in test if q["lang"] == lang]) for lang in langs}
    non_it = [q for q in test if q["lang"] != "it"]
    stats = {
        f"{a}_vs_{b}_{m}_{lang}": paired_randomization_test(
            [runs[a][q["qid"]].metrics[m] for q in in_scope if lang in ("all", q["lang"])],
            [runs[b][q["qid"]].metrics[m] for q in in_scope if lang in ("all", q["lang"])])
        for a, b in (("S3", "S2"), ("S3", "S1"), ("S3f", "S2"), ("S3f", "S1")) for m in ("ndcg@10", "recall@10")
        for lang in ("all", "en", "ar")
    }
    new_lines = []
    if settings.llm_usage_log.exists():
        with open(settings.llm_usage_log, encoding="utf-8") as f:
            f.seek(usage_start)
            new_lines = []
            for x in f.read().splitlines():
                try:
                    new_lines.append(json.loads(x))
                except json.JSONDecodeError:  # line still being written by another process
                    continue
    fresh = [x for x in new_lines if not x["cached"] and x["purpose"] == "query_translation"]
    ts = timestamp()
    report = {
        "generated_at": ts,
        "test_split_sha256": test_hash("unibridge")[0],
        "systems": {"S1": "dense, original question", "S2": "hybrid RRF, original question",
                    "S3": "S2 on the LLM Italian translation (it questions: S2)",
                    "S3f": "RRF of S2(original) and S2(translation), as the answer service"},
        "llm": {"provider": settings.llm_provider, "model": settings.llm_model, "temperature": 0, "max_output_tokens": 200,
                "prompt": "p14_search.answer.prompts.TRANSLATE_SYSTEM"},
        "tuning_on_test": "none: fixed prompt from phase 4, S2 thresholds from the tuning-split calibration",
        "n_test_queries": len(test),
        "n_translated": len(translations),
        "n_by_lang": {lang: sum(1 for q in test if q["lang"] == lang) for lang in langs},
        "overall": agg(test),
        "non_italian": agg(non_it),
        "by_lang": by_lang,
        "randomization_tests": stats,
        "translation_cost": {
            "calls": sum(1 for x in new_lines if x["purpose"] == "query_translation"), "non_cached_calls": len(fresh),
            "input_tokens": sum(x["input_tokens"] for x in fresh), "output_tokens": sum(x["output_tokens"] for x in fresh),
            "estimated_cost_usd": round(sum(x["cost_usd"] or 0 for x in fresh), 6),
        },
    }
    write_json(RESULTS / f"translation_{ts}.json", report)
    write_json(RESULTS / "translation_latest.json", report)
    cols = ["recall@10", "mrr@10", "ndcg@10", "correct_source@3"]
    with open(RESULTS / f"translation_{ts}_per_query.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["qid", "lang", "source", "type", "system", "insufficient_evidence", *cols, "top3_passages"])
        for q in test:
            for s in SYSTEMS:
                r = runs[s][q["qid"]]
                w.writerow([q["qid"], q["lang"], q["source"], q["type"], s, r.insufficient_evidence,
                            *[r.metrics.get(c) for c in cols], " ".join(r.ranked[:3])])
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["qid", "lang", "question", "italian_translation", "llm_generated", "translation_ok (y/n)", "notes"])
        for q in non_it:
            w.writerow([q["qid"], q["lang"], q["query"], translations[q["qid"]], "true", "", ""])
    keys = ("ndcg@10", "recall@10", "mrr@10", "correct_source@3", "abstention_correctness", "false_abstention_rate")
    print("by_lang ndcg@10", json.dumps({lang: {s: by_lang[lang][s]["ndcg@10"] for s in SYSTEMS} for lang in langs}))
    print("by_lang recall@10", json.dumps({lang: {s: by_lang[lang][s]["recall@10"] for s in SYSTEMS} for lang in langs}))
    print("overall", json.dumps({s: {m: report["overall"][s][m] for m in keys} for s in SYSTEMS}))
    print("cost", report["translation_cost"], f"\n-> eval/results/unibridge/translation_{ts}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
