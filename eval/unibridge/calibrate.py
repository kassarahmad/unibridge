"""Calibrate the UniBridge insufficient_evidence thresholds on the TUNING split only (same method as
eval/calibrate_threshold.py: maximise balanced accuracy between in-scope and out-of-scope tuning queries).

Usage:
    python eval/unibridge/calibrate.py   -> eval/results/unibridge/calibration.json (read by the UniBridge profile)
"""

from __future__ import annotations

import sys

from ub_common import CALIBRATION, RESULTS, principals, queries, search_service, timestamp, unibridge_settings, write_json

from calibrate_threshold import best_threshold  # noqa: E402  (eval/ is on sys.path via ub_common)


def main() -> int:
    settings = unibridge_settings().model_copy(update={"ie_min_dense": 0.0, "ie_min_bm25": 0.0})
    search = search_service(settings=settings)
    users = principals(settings)
    tuning = queries("tuning")
    signals = {"dense": {"in": [], "out": []}, "bm25": {"in": [], "out": []}}
    per_query = []
    for q in tuning:
        r = search.rank_all(q["query"], users[q["principal"]], 10, ("S2",))["S2"]
        side = "out" if q["type"] == "out_of_scope" else "in"
        signals["dense"][side].append(r.top_dense or 0.0)
        signals["bm25"][side].append(r.top_bm25 or 0.0)
        per_query.append({"qid": q["qid"], "lang": q["lang"], "type": q["type"], "top_dense": r.top_dense, "top_bm25": r.top_bm25})
    dense = best_threshold(signals["dense"]["in"], signals["dense"]["out"])
    bm25 = best_threshold(signals["bm25"]["in"], signals["bm25"]["out"])
    report = {
        "split": "tuning",
        "n_queries": len(tuning),
        "embedding_model": search.dense.embedder.name,
        "ie_min_dense": dense["threshold"],
        "ie_min_bm25": bm25["threshold"],
        "dense": dense,
        "bm25": bm25,
        "signal_ranges": {k: {side: [round(min(v), 4), round(max(v), 4)] for side, v in s.items()} for k, s in signals.items()},
        "per_query": per_query,
    }
    write_json(RESULTS / f"calibration_{timestamp()}.json", report)
    write_json(CALIBRATION, report)
    print(f"IE_MIN_DENSE={dense['threshold']}  {dense}")
    print(f"IE_MIN_BM25={bm25['threshold']}  {bm25}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
