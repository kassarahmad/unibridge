"""Evaluate UniBridge answers on the frozen TEST split.

Configurations (same retrieval: S2 hybrid, role visitor):
- extractive        no LLM
- llm               LLM answer, citations parsed but not verified
- llm_verified      LLM answer + verifier (citation check + support check)          [default of the API]
- llm_verified_noqt as llm_verified, without the Italian translation of en/ar queries for retrieval

Metrics (definitions in docs/REPORT_UNIBRIDGE.md, section Evaluation):
- citation_precision: shown sentences whose cited passages include a relevant passage (qrels grade >= 1)
- uncited_sentence_rate: shown sentences without a valid citation
- judge_unsupported_rate: shown sentences that the LLM judge (same model, support prompt) says are NOT supported
  by their cited passage. Biased (same model as the generator) - see the human review sample.
- idk_correct_oos: out-of-scope questions answered "I don't know"; idk_false_in_scope: in-scope questions
  answered "I don't know"
- answer_language_correct: non-empty answers whose detected language equals the question language
- source_recall@k: share of relevant (grade 2) passages among the passages given to the answer step
- cost per answer (estimated USD, non-cached calls) and latency

Usage:
    python eval/unibridge/eval_answers.py [--configs extractive,llm,llm_verified,llm_verified_noqt] [--limit N]
Outputs: eval/results/unibridge/answers_<timestamp>.json, answers_<timestamp>_per_query.csv, answers_latest.json,
         eval/results/unibridge/llm_cost.json, eval/review/unibridge_answers_review.csv (sample for human review)
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
import time
from collections import Counter

from ub_common import RESULTS, ROOT, load_qrels, principals, queries, timestamp, unibridge_settings, write_json

from freeze_test import verify  # noqa: E402  (eval/ is on sys.path via ub_common)

from p14_search.answer import prompts
from p14_search.answer.language import detect
from p14_search.answer.llm import LLMError
from p14_search.answer.service import AnswerService
from p14_search.answer.verifier import is_yes
from p14_search.evaluation.metrics import percentile
from p14_search.models import AnswerRequest
from p14_search.services import build_services

CONFIGS = ("extractive", "llm", "llm_verified", "llm_verified_noqt")
REVIEW = ROOT / "eval" / "review" / "unibridge_answers_review.csv"


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 4) if xs else None


def judge(llm, passage_text: str, sentence: str) -> bool | None:
    try:
        system, user = prompts.support_prompt(passage_text, sentence)
        return is_yes(llm.complete(system, user, 3, "eval_judge").text)
    except LLMError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", default=",".join(CONFIGS))
    parser.add_argument("--limit", type=int, default=None, help="first N test queries (smoke runs)")
    args = parser.parse_args()
    if not verify("unibridge"):
        raise SystemExit("test split changed since it was frozen")
    settings = unibridge_settings()
    services = build_services(settings)
    llm = services.llm
    configs = [c for c in args.configs.split(",") if c]
    skipped = {}
    if llm is None:
        skipped = {c: "no LLM configured" for c in configs if c != "extractive"}
    else:
        try:
            llm.complete("Reply with: ok", "ok", 2, "probe")
        except LLMError as exc:
            skipped = {c: f"LLM not usable: {exc.__cause__.__class__.__name__ if exc.__cause__ else exc}" for c in configs if c != "extractive"}
    configs = [c for c in configs if c not in skipped]
    users = principals(settings)
    test = queries("test")[: args.limit]
    qrels = load_qrels()
    usage_start = settings.llm_usage_log.stat().st_size if settings.llm_usage_log.exists() else 0

    services_by_config = {
        "llm_verified_noqt": AnswerService(services.search, llm, services.handoff, settings.model_copy(update={"answer_query_translation": False})),
    }
    rows, per_config = [], {}
    for config in configs:
        svc = services_by_config.get(config, services.answer)
        mode = {"llm_verified_noqt": "llm_verified"}.get(config, config)
        results = []
        for q in test:
            t0 = time.perf_counter()
            r = svc.answer(AnswerRequest(query=q["query"], mode=mode), users[q["principal"]], f"eval-{config}-{q['qid']}-{time.time_ns()}")
            wall = (time.perf_counter() - t0) * 1000
            grades = qrels[q["qid"]]
            text_of = {s.passage_id: s.text for s in r.sources}
            shown = r.sentences
            cited_ok = [any(grades.get(pid, 0) >= 1 for pid in s.passage_ids) for s in shown if s.passage_ids]
            uncited = sum(1 for s in shown if not s.passage_ids)
            judged = []
            if llm is not None and "llm" not in skipped.get(config, ""):
                for s in shown:
                    if s.passage_ids:
                        judged.append(judge(llm, "\n\n".join(text_of[p] for p in s.passage_ids if p in text_of), s.text))
                    else:
                        judged.append(False)
            relevant = {p for p, g in grades.items() if g >= 2}
            res = {
                "qid": q["qid"], "lang": q["lang"], "source": q["source"], "type": q["type"], "config": config,
                "mode": r.mode, "idk": r.insufficient_evidence, "n_sentences": len(shown),
                "citation_precision": mean([1.0 if ok else 0.0 for ok in cited_ok]),
                "uncited_rate": round(uncited / len(shown), 4) if shown else None,
                "judge_unsupported_rate": mean([0.0 if j else 1.0 for j in judged if j is not None]) if judged else None,
                "answer_lang": detect(r.answer_text) if r.answer_text else None,
                "lang_correct": (detect(r.answer_text) == q["lang"]) if r.answer_text else None,
                "source_recall": round(len(relevant & set(text_of)) / len(relevant), 4) if relevant else None,
                "cost_usd": r.llm.cost_usd if r.llm else 0.0,
                "llm_calls": r.llm.calls if r.llm else 0,
                "cached_calls": r.llm.cached_calls if r.llm else 0,
                "latency_ms": r.latency_ms, "wall_ms": round(wall, 1),
                "handoff_office": r.handoff.draft.office_id if r.handoff and r.handoff.draft else ("out_of_scope" if r.handoff else None),
                "answer": r.answer_text, "sentences": [[s.text, s.passage_ids] for s in shown],
            }
            results.append(res)
        rows += results
        ins = [x for x in results if x["type"] != "out_of_scope"]
        oos = [x for x in results if x["type"] == "out_of_scope"]
        answered = [x for x in results if not x["idk"]]

        def summary(subset_in, subset_all):
            ans = [x for x in subset_all if not x["idk"]]
            sent_w = [x for x in ans if x["n_sentences"]]
            return {
                "n": len(subset_all),
                "answered": len(ans),
                "citation_precision": mean(x["citation_precision"] for x in sent_w),
                "uncited_sentence_rate": mean(x["uncited_rate"] for x in sent_w),
                "judge_unsupported_rate": mean(x["judge_unsupported_rate"] for x in sent_w),
                "answer_language_correct": mean(1.0 if x["lang_correct"] else 0.0 for x in ans),
                "idk_false_in_scope": mean(1.0 if x["idk"] else 0.0 for x in subset_in),
                "source_recall": mean(x["source_recall"] for x in subset_in),
            }

        per_config[config] = {
            **summary(ins, results),
            "idk_correct_oos": mean(1.0 if x["idk"] else 0.0 for x in oos),
            "n_out_of_scope": len(oos),
            "oos_handoff": dict(Counter(x["handoff_office"] for x in oos)),
            "cost_usd_total": round(sum(x["cost_usd"] or 0 for x in results), 6),
            "cost_usd_per_answer": round(sum(x["cost_usd"] or 0 for x in results) / max(len(results), 1), 6),
            "llm_calls_per_answer": round(sum(x["llm_calls"] for x in results) / max(len(results), 1), 2),
            "cached_call_share": round(sum(x["cached_calls"] for x in results) / max(sum(x["llm_calls"] for x in results), 1), 4),
            "latency_ms_p50": round(percentile([x["latency_ms"] for x in results], 50), 1),
            "latency_ms_p95": round(percentile([x["latency_ms"] for x in results], 95), 1),
            "by_lang": {lang: summary([x for x in ins if x["lang"] == lang], [x for x in results if x["lang"] == lang])
                        for lang in ("it", "en", "ar")},
            "answered_share": round(len(answered) / max(len(results), 1), 4),
        }
        print(config, json.dumps({k: v for k, v in per_config[config].items() if k != "by_lang"}))

    # cost of this run, from the usage log lines appended by it
    new_lines = []
    if settings.llm_usage_log.exists():
        with open(settings.llm_usage_log, encoding="utf-8") as f:
            f.seek(usage_start)
            new_lines = [json.loads(x) for x in f.read().splitlines() if x.strip()]
    fresh = [x for x in new_lines if not x["cached"]]
    run_cost = {
        "calls": len(new_lines), "non_cached_calls": len(fresh),
        "input_tokens": sum(x["input_tokens"] for x in fresh), "output_tokens": sum(x["output_tokens"] for x in fresh),
        "estimated_cost_usd": round(sum(x["cost_usd"] or 0 for x in fresh), 6),
        "by_purpose": {p: sum(1 for x in fresh if x["purpose"] == p) for p in sorted({x["purpose"] for x in fresh})},
    }
    ts = timestamp()
    report = {
        "generated_at": ts, "n_test_queries": len(test), "role": "visitor",
        "llm": {"provider": settings.llm_provider or None, "model": settings.llm_model or None,
                "price_usd_per_mtok": list(llm.price) if llm and llm.price else None},
        "skipped_configs": skipped, "configs": per_config, "run_llm_usage": run_cost,
        "calibration": {"ie_min_dense": settings.ie_min_dense, "ie_min_bm25": settings.ie_min_bm25},
    }
    write_json(RESULTS / f"answers_{ts}.json", report)
    write_json(RESULTS / "answers_latest.json", report)
    with open(RESULTS / f"answers_{ts}_per_query.csv", "w", newline="", encoding="utf-8") as f:
        cols = [k for k in rows[0] if k != "sentences"] if rows else []
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    # cumulative LLM spend of the project (all runs), from the usage log
    if settings.llm_usage_log.exists():
        all_rows = [json.loads(x) for x in settings.llm_usage_log.read_text(encoding="utf-8").splitlines() if x.strip()]
        allf = [x for x in all_rows if not x["cached"]]
        write_json(RESULTS / "llm_cost.json", {
            "source": "logs/llm_usage.jsonl (not committed); estimated with the price table in src/p14_search/answer/llm.py",
            "updated_at": ts, "non_cached_calls": len(allf), "input_tokens": sum(x["input_tokens"] for x in allf),
            "output_tokens": sum(x["output_tokens"] for x in allf),
            "estimated_cost_usd": round(sum(x["cost_usd"] or 0 for x in allf), 6),
            "models": sorted({f"{x['provider']}:{x['model']}" for x in allf}),
        })
    # human review sample: up to 30 answered sentences of the default configuration
    sample_src = [x for x in rows if x["config"] == "llm_verified" and not x["idk"]] or [x for x in rows if not x["idk"]]
    rng = random.Random(14)
    sample = rng.sample(sample_src, min(30, len(sample_src)))
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["qid", "config", "lang", "question", "answer_sentence", "cited_passage_ids", "supported_by_passage (y/n)", "notes"])
        qtext = {q["qid"]: q["query"] for q in test}
        for x in sample:
            for text, pids in x["sentences"]:
                w.writerow([x["qid"], x["config"], x["lang"], qtext[x["qid"]], text, " ".join(pids), "", ""])
    print("run usage", run_cost, "\nskipped", skipped, f"\n-> eval/results/unibridge/answers_{ts}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
