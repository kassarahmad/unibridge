"""Total estimated LLM spend of the project, from the usage log -> eval/results/unibridge/llm_cost.json.

Counts every non-cached call in logs/llm_usage.jsonl (all evaluations, translations, demo and screenshots), priced with
the table in src/p14_search/answer/llm.py. Run it last, after the evaluations.

Usage:
    python eval/unibridge/llm_cost.py
"""

from __future__ import annotations

import sys
from collections import Counter

from ub_common import RESULTS, timestamp, unibridge_settings, write_json

from p14_search.answer.llm import read_usage


def main() -> int:
    rows = read_usage(unibridge_settings().llm_usage_log)
    fresh = [x for x in rows if not x["cached"]]
    report = {
        "source": "logs/llm_usage.jsonl (not committed); estimated with the price table in src/p14_search/answer/llm.py",
        "updated_at": timestamp(),
        "non_cached_calls": len(fresh),
        "input_tokens": sum(x["input_tokens"] for x in fresh),
        "output_tokens": sum(x["output_tokens"] for x in fresh),
        "estimated_cost_usd": round(sum(x["cost_usd"] or 0 for x in fresh), 6),
        "models": sorted({f"{x['provider']}:{x['model']}" for x in fresh}),
        "calls_by_purpose": dict(sorted(Counter(x["purpose"] for x in fresh).items())),
    }
    write_json(RESULTS / "llm_cost.json", report)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
