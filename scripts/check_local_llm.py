"""Manual check of the local LLM provider: asks the running UniBridge API one question in Italian, English and
Arabic and records which provider answered, the cost, and whether the internet was reachable at that moment.

Run it once online and once with the network switched off: the same answers with `internet_reachable: false`,
provider `local` and no cached call show that the whole pipeline runs on this machine.

Before: start the LM Studio server with the model loaded, Qdrant, and the API with LLM_PROVIDER=local.

Usage:
    python scripts/check_local_llm.py [--api http://127.0.0.1:8001] [--out docs/evidence/unibridge/local_llm_check.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = {
    "it": "Entro quando devo presentare la domanda di borsa di studio ERDIS?",
    "en": "What is the deadline to apply for the ERDIS scholarship?",
    "ar": "ما هو الموعد النهائي لتقديم طلب المنحة الدراسية ERDIS؟",
}
# Public hosts on port 443: a DNS resolver, the OpenAI API and the Hugging Face hub.
PROBES = [("1.1.1.1", 443), ("api.openai.com", 443), ("huggingface.co", 443)]


def internet_reachable(timeout: float = 3.0) -> dict:
    out = {}
    for host, port in PROBES:
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            out[host] = True
        except OSError:
            out[host] = False
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8001")
    ap.add_argument("--key", default="demo-ub-visitor")
    ap.add_argument("--out", default="docs/evidence/unibridge/local_llm_check.json")
    args = ap.parse_args()

    probes = internet_reachable()
    answers = []
    for lang, question in QUESTIONS.items():
        start = time.perf_counter()
        r = requests.post(f"{args.api}/v1/answer", json={"query": question}, headers={"X-API-Key": args.key}, timeout=600)
        r.raise_for_status()
        body = r.json()
        answers.append({
            "expected_language": lang, "query": question, "seconds": round(time.perf_counter() - start, 2),
            "language": body["language"], "mode": body["mode"], "answer_text": body["answer_text"],
            "sentences": [{"text": s["text"], "citations": len(s["passage_ids"]), "supported": s.get("supported")}
                          for s in body["sentences"]],
            "query_italian": body.get("query_italian"), "verification": body.get("verification"), "llm": body.get("llm"),
        })
    llm = [a["llm"] or {} for a in answers]
    report = {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "api": args.api,
        "internet_probes": probes,
        "internet_reachable": any(probes.values()),
        "all_answered_by_local_llm": all(x.get("provider") == "local" and a["mode"] == "llm_verified" for x, a in zip(llm, answers)),
        "cached_calls": sum(x.get("cached_calls", 0) for x in llm),
        "cost_usd": sum(x.get("cost_usd") or 0.0 for x in llm),
        "answers": answers,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"internet reachable: {report['internet_reachable']}  {probes}")
    for a in answers:
        x = a["llm"] or {}
        print(f"{a['expected_language']}: detected {a['language']}, mode {a['mode']}, {len(a['sentences'])} cited sentence(s), "
              f"provider {x.get('provider')}:{x.get('model')}, {x.get('calls')} call(s), {x.get('cached_calls')} cached, "
              f"{x.get('cost_usd')} USD, {a['seconds']} s")
    print(f"all answered by the local LLM: {report['all_answered_by_local_llm']}; written {out.relative_to(ROOT)}")
    return 0 if report["all_answered_by_local_llm"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
