"""Corpus statistics from the ingested SQLite store -> eval/results/corpus_stats.json (used in docs/DATA.md).

Usage:
    python scripts/corpus_stats.py                      # P14 (D1) corpus
    python scripts/corpus_stats.py --profile unibridge  # -> eval/results/unibridge/corpus_stats.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from p14_search.config import get_settings
from p14_search.indexing.store import Store, now_iso
from p14_search.ingestion.parser import _text_quality

ROOT = Path(__file__).resolve().parents[1]
FORMAT = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/html": "html",
    "text/plain": "txt",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("p14", "unibridge"), default="p14")
    args = parser.parse_args()
    unibridge = args.profile == "unibridge"
    if unibridge:
        from p14_search.unibridge_profile import unibridge_settings

        settings = unibridge_settings()
    else:
        settings = get_settings()
    store = Store(settings.sqlite_path)
    rows = store.query(
        """SELECT d.document_id, d.source_id, d.access_level, d.office, d.synthetic, v.media_type, v.text_chars, v.bytes,
                  (SELECT COUNT(*) FROM passages p WHERE p.document_id = d.document_id AND p.indexed = 1) AS passages,
                  (SELECT COUNT(*) FROM passages p WHERE p.document_id = d.document_id AND p.indexed = 1 AND p.section IS NOT NULL) AS with_section,
                  (SELECT AVG(LENGTH(p.text)) FROM passages p WHERE p.document_id = d.document_id AND p.indexed = 1) AS avg_len
           FROM documents d JOIN document_versions v ON v.document_id = d.document_id AND v.document_version = d.current_version
           WHERE d.status = 'approved'"""
    )
    groups: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: {"documents": 0, "passages": 0, "text_chars": 0}))
    for r in rows:
        for dim, key in (("source", r["source_id"]), ("format", f"{r['source_id']}/{FORMAT[r['media_type']]}"),
                         ("access_level", r["access_level"]), ("office", r["office"])):
            g = groups[dim][key]
            g["documents"] += 1
            g["passages"] += r["passages"]
            g["text_chars"] += r["text_chars"]
    total_passages = sum(r["passages"] for r in rows)
    out = {
        "generated_at": now_iso(),
        "index_snapshot_id": store.get_meta("index_snapshot_id"),
        "totals": {
            "documents": len(rows),
            "passages": total_passages,
            "text_chars": sum(r["text_chars"] for r in rows),
            "raw_bytes": sum(r["bytes"] for r in rows),
            "passages_with_section_share": round(sum(r["with_section"] for r in rows) / max(total_passages, 1), 4),
            "mean_passage_chars": round(sum((r["avg_len"] or 0) * r["passages"] for r in rows) / max(total_passages, 1), 1),
        },
        **{dim: dict(sorted(v.items())) for dim, v in groups.items()},
        "largest_documents": [
            {"document_id": r["document_id"], "passages": r["passages"]}
            for r in sorted(rows, key=lambda r: -r["passages"])[:5]
        ],
    }
    # Heuristic share of passages that are not readable prose (tables, lists, garbled font pages): long passages
    # with almost no function words. Reported in DATA.md as a data-quality indicator.
    real = "ub" if unibridge else "d1a"
    d1a = store.query(f"SELECT text FROM passages WHERE indexed = 1 AND document_id LIKE '{real}:%'")
    non_prose = sum(1 for r in d1a if len(r["text"]) > 200 and _text_quality(r["text"]) < 0.02)
    out["quality"] = {f"{real}_passages": len(d1a), f"{real}_non_prose_passages": non_prose,
                      f"{real}_non_prose_share": round(non_prose / max(len(d1a), 1), 4)}
    path = ROOT / "eval" / "results" / "corpus_stats.json"
    if unibridge:
        record = json.loads((ROOT / "data/raw/unibridge/fetch_record.json").read_text(encoding="utf-8"))
        for dim in ("publisher", "lang", "licence", "type"):
            counts: dict[str, int] = defaultdict(int)
            for d in record["documents"]:
                counts[d[dim]] += 1
            out[f"real_documents_by_{dim}"] = dict(sorted(counts.items()))
        out["fetch_failures"] = record["failures"]
        path = ROOT / "eval" / "results" / "unibridge" / "corpus_stats.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out["totals"], indent=2))
    print(f"-> {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
