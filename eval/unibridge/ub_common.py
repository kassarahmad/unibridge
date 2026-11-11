"""Helpers shared by the eval/unibridge/ scripts: UniBridge queries, qrels, search service and principals."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from common import search_service, timestamp, write_json  # noqa: E402,F401  (P14 eval helpers)

from p14_search.evaluation.runner import principals_by_name  # noqa: E402
from p14_search.unibridge_profile import CALIBRATION, unibridge_settings  # noqa: E402

RESULTS = ROOT / "eval" / "results" / "unibridge"
QUERIES = ROOT / "eval" / "queries" / "unibridge_queries.jsonl"
QRELS = ROOT / "eval" / "qrels" / "unibridge_qrels.json"
__all__ = ["CALIBRATION", "RESULTS", "ROOT", "load_qrels", "principals", "queries", "search_service", "timestamp",
           "unibridge_settings", "write_json"]


def queries(split: str | None = None) -> list[dict]:
    rows = [json.loads(line) for line in QUERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [q for q in rows if split is None or q["split"] == split]


def load_qrels() -> dict[str, dict[str, int]]:
    return json.loads(QRELS.read_text(encoding="utf-8"))["qrels"]


def principals(settings) -> dict:
    return principals_by_name(settings.principals_path)
