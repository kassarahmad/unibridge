"""UniBridge in the languages added after phase 8, on the frozen multilingual test set (unibridge_ml).

For every language: language identification accuracy; retrieval with S1 (dense), S2 (hybrid) and S3f (S2 fused with
S2 on the LLM Italian translation, as the answer service); answers in mode llm_verified (the API default).
The Italian source questions are evaluated the same way as a reference row ("it").
Relevance judgments are those of the source question. Nothing is tuned: prompts, thresholds and the verifier are
the ones of phases 4-8. The answer step has its own response cache (data/processed/llm_cache/eval_ml), so the
first run measures a cold start. Costs are summed from the calls of this evaluation (not from the shared usage
log), so several workers can run at the same time.

Usage:
    python eval/unibridge/eval_multilingual.py                       # everything in one process
    python eval/unibridge/eval_multilingual.py --langs it,fr,es --part a   # one worker (run several in parallel)
    python eval/unibridge/eval_multilingual.py --merge                # combine the workers' parts
Outputs: eval/results/unibridge/multilingual_<timestamp>.json, multilingual_<timestamp>_per_query.csv,
         multilingual_latest.json (parts: eval/results/unibridge/multilingual_parts/)
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time

from ub_common import CALIBRATION, RESULTS, ROOT, load_qrels, principals, queries, timestamp, unibridge_settings, write_json

from freeze_test import test_hash, verify  # noqa: E402  (eval/ is on sys.path via ub_common)

from p14_search.evaluation.metrics import paired_randomization_test, percentile
from p14_search.evaluation.runner import K, QueryRun, aggregate, score
from p14_search.i18n import LANGS

ML_QUERIES = ROOT / "eval" / "queries" / "unibridge_queries_ml.jsonl"
PARTS = RESULTS / "multilingual_parts"
SYSTEMS = ("S1", "S2", "S3f")


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 4) if xs else None


def test_questions() -> list[dict]:
    ml = [json.loads(line) for line in ML_QUERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
    source_ids = {q["translation_of"] for q in ml}
    reference = [{**q, "translation_of": q["qid"]} for q in queries("test") if q["qid"] in source_ids and q["lang"] == "it"]
    return reference + ml


def work(langs: list[str], part: str) -> None:
    from p14_search.answer.language import detect
    from p14_search.answer.llm import LLMClient
    from p14_search.answer.service import AnswerService, translate_query
    from p14_search.models import AnswerRequest
    from p14_search.retrieval.retrievers import rrf_fuse
    from p14_search.services import build_services

    settings = unibridge_settings()
    services = build_services(settings)
    llm = services.llm
    if llm is None:
        raise SystemExit("needs an LLM: set LLM_PROVIDER, LLM_MODEL and LLM_API_KEY in .env")
    search = services.search
    client = LLMClient(llm.provider, settings.llm_cache_dir / "eval_ml", settings.llm_usage_log, settings.llm_budget_usd, llm.price)
    answerer = AnswerService(search, client, services.handoff, settings)
    users = principals(settings)
    qrels = load_qrels()
    test = [q for q in test_questions() if q["lang"] in langs]
    rows, retrieval_cost = [], 0.0
    for n, q in enumerate(test, 1):
        p = users[q["principal"]]
        grades = qrels[q["translation_of"]]
        first = search.rank_all(q["query"], p, K, ("S1", "S2"))
        runs = {s: QueryRun(q["qid"], s, [h.passage_id for h in first[s].hits], first[s].insufficient_evidence, None, None)
                for s in ("S1", "S2")}
        s2 = first["S2"]
        if q["lang"] == "it":
            fused, ie = s2.hits, s2.insufficient_evidence
        else:
            tr = translate_query(llm, q["query"])
            retrieval_cost += 0 if tr.cached else (tr.cost_usd or 0)
            second = search.rank_all(tr.text.strip(), p, K, ("S2",))["S2"]
            fused, ie = rrf_fuse({"original": s2.hits, "italian": second.hits}, K), s2.insufficient_evidence and second.insufficient_evidence
        runs["S3f"] = QueryRun(q["qid"], "S3f", [h.passage_id for h in fused], ie, None, None)
        metrics = {s: score(r, grades, q["type"] != "out_of_scope") for s, r in runs.items()}

        t0 = time.perf_counter()
        a = answerer.answer(AnswerRequest(query=q["query"], mode="llm_verified"), p, f"eval-ml-{q['qid']}-{time.time_ns()}")
        cited = [any(grades.get(pid, 0) >= 1 for pid in s.passage_ids) for s in a.sentences if s.passage_ids]
        rows.append({
            "qid": q["qid"], "lang": q["lang"], "type": q["type"], "translation_of": q["translation_of"],
            "detected": detect(q["query"]), "idk": a.insufficient_evidence, "n_sentences": len(a.sentences),
            "citation_precision": mean([1.0 if ok else 0.0 for ok in cited]),
            "answer_text_lang": detect(a.answer_text) if a.answer_text else None,
            "cost_usd": a.llm.cost_usd if a.llm and a.llm.cost_usd else 0.0, "llm_calls": a.llm.calls if a.llm else 0,
            "cached_calls": a.llm.cached_calls if a.llm else 0,
            "latency_ms": a.latency_ms, "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
            "metrics": metrics, "answer": a.answer_text,
        })
        if n % 25 == 0:
            print(f"[{part}] {n}/{len(test)}", flush=True)
    PARTS.mkdir(parents=True, exist_ok=True)
    write_json(PARTS / f"{part}.json", {"langs": langs, "retrieval_translation_cost_usd": round(retrieval_cost, 6), "rows": rows})
    print(f"[{part}] done: {len(rows)} questions")


def merge() -> None:
    parts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PARTS.glob("*.json"))]
    rows = [r for part in parts for r in part["rows"]]
    test = test_questions()
    missing = {q["qid"] for q in test} - {r["qid"] for r in rows}
    if missing:
        raise SystemExit(f"{len(missing)} questions not evaluated yet, e.g. {sorted(missing)[:3]}")
    by_qid = {r["qid"]: r for r in rows}
    runs = {s: {r["qid"]: QueryRun(r["qid"], s, [], r["metrics"][s]["insufficient_evidence"], None, None) for r in rows} for s in SYSTEMS}
    for s in SYSTEMS:
        for qid, run in runs[s].items():
            run.metrics = by_qid[qid]["metrics"][s]
    by_lang: dict[str, list[dict]] = {}
    for q in test:
        by_lang.setdefault(q["lang"], []).append(q)

    def summary(lang_rows: list[dict], lang_qs: list[dict]) -> dict:
        ins = [x for x in lang_rows if x["type"] != "out_of_scope"]
        oos = [x for x in lang_rows if x["type"] == "out_of_scope"]
        answered = [x for x in lang_rows if not x["idk"]]
        return {
            "n": len(lang_rows), "n_in_scope": len(ins), "n_out_of_scope": len(oos),
            "detection_accuracy": mean(1.0 if x["detected"] == x["lang"] else 0.0 for x in lang_rows),
            "retrieval": {s: {m: aggregate(runs[s], lang_qs)[m] for m in ("ndcg@10", "recall@10", "correct_source@3",
                                                                           "false_abstention_rate", "abstention_correctness")}
                          for s in SYSTEMS},
            "answered": len(answered),
            "citation_precision": mean(x["citation_precision"] for x in answered if x["n_sentences"]),
            # the answer is in the question's language (same detector; answers may quote Italian terms)
            "answer_language_correct": mean(1.0 if x["answer_text_lang"] == x["lang"] else 0.0 for x in answered),
            "idk_false_in_scope": mean(1.0 if x["idk"] else 0.0 for x in ins),
            "idk_correct_oos": mean(1.0 if x["idk"] else 0.0 for x in oos),
            "cost_usd_per_answer": round(sum(x["cost_usd"] for x in lang_rows) / max(len(lang_rows), 1), 6),
            "latency_ms_p50": round(percentile([x["latency_ms"] for x in lang_rows], 50), 1),
        }

    per_lang = {lang: summary([by_qid[q["qid"]] for q in qs], qs) for lang, qs in by_lang.items()}
    new = [q for q in test if q["lang"] != "it"]
    in_new = [q for q in new if q["type"] != "out_of_scope"]
    stats = {
        f"S3f_vs_{b}_{m}_new_languages": paired_randomization_test(
            [runs["S3f"][q["qid"]].metrics[m] for q in in_new], [runs[b][q["qid"]].metrics[m] for q in in_new])
        for b in ("S2", "S1") for m in ("ndcg@10", "recall@10")
    }
    answer_cost = sum(r["cost_usd"] for r in rows)
    retrieval_cost = sum(p["retrieval_translation_cost_usd"] for p in parts)
    settings = unibridge_settings()
    ts = timestamp()
    report = {
        "generated_at": ts,
        "test_split_sha256": {"unibridge_ml": test_hash("unibridge_ml")[0], "unibridge": test_hash("unibridge")[0]},
        "llm": {"provider": settings.llm_provider, "model": settings.llm_model},
        "tuning_on_test": "none: prompts, thresholds and verifier from phases 4-8",
        "languages": [lang for lang in LANGS if lang in by_lang],
        "n_questions": len(test),
        "n_new_language_questions": len(new),
        "by_lang": per_lang,
        "new_languages": summary([by_qid[q["qid"]] for q in new], new),
        "randomization_tests": stats,
        "cold_run": sum(r["cached_calls"] for r in rows) == 0,
        "cost_usd": {"answers": round(answer_cost, 6), "retrieval_translations": round(retrieval_cost, 6),
                     "total": round(answer_cost + retrieval_cost, 6)},
    }
    write_json(RESULTS / f"multilingual_{ts}.json", report)
    write_json(RESULTS / "multilingual_latest.json", report)
    with open(RESULTS / f"multilingual_{ts}_per_query.csv", "w", newline="", encoding="utf-8") as f:
        cols = [k for k in rows[0] if k != "metrics"] + [f"ndcg@10_{s}" for s in SYSTEMS]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, **{f"ndcg@10_{s}": r["metrics"][s].get("ndcg@10") for s in SYSTEMS}})
    for lang, s in per_lang.items():
        r = s["retrieval"]
        print(f"{lang}: detect {s['detection_accuracy']} ndcg S2 {r['S2']['ndcg@10']} S3f {r['S3f']['ndcg@10']} "
              f"answered {s['answered']}/{s['n']} cit {s['citation_precision']} lang {s['answer_language_correct']} "
              f"idk_oos {s['idk_correct_oos']}")
    print("cost", report["cost_usd"], "cold run", report["cold_run"], f"\n-> eval/results/unibridge/multilingual_{ts}.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--langs", default=None, help="comma-separated languages for one worker")
    parser.add_argument("--part", default="all", help="name of the worker's part file")
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    if not verify("unibridge_ml") or not verify("unibridge"):
        raise SystemExit("a test split changed since it was frozen")
    if not CALIBRATION.exists():
        raise SystemExit("run eval/unibridge/calibrate.py first")
    if args.merge:
        merge()
    elif args.langs:
        work(args.langs.split(","), args.part)
    else:
        work(list(LANGS), "all")
        merge()
    return 0


if __name__ == "__main__":
    sys.exit(main())
