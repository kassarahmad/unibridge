"""Ingest and approve the UniBridge corpus (real public documents + synthetic restricted documents) into the
UniBridge profile (data/processed/unibridge.sqlite, Qdrant collection unibridge_passages).

Same pipeline, ids, ACL and citation logic as P14 (scripts/ingest_corpus.py). Approval is a SIMULATED owner
action recorded in approval_log with the note below.

Prerequisites: python scripts/fetch_corpus_unibridge.py; docker compose up -d
Usage:
    python scripts/ingest_unibridge.py            # idempotent: unchanged documents are skipped
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

from p14_search.models import AccessLevel, IngestDocument
from p14_search.security.principals import Principal
from p14_search.services import build_services
from p14_search.unibridge_profile import unibridge_settings

ROOT = Path(__file__).resolve().parents[1]
MEDIA = {"pdf": "application/pdf", "html": "text/html", "txt": "text/plain"}
OWNER = {
    "scholarship": "ERDIS Marche - Ufficio Diritto allo studio",
    "student_office": "UNICAM - Segreteria studenti",
    "international": "UNICAM - International Welcome Office",
}
APPROVAL_NOTE = "simulated owner approval (scripts/ingest_unibridge.py)"


def file_payload(path: Path) -> dict:
    return {"filename": path.name, "media_type": MEDIA[path.suffix[1:]], "content_base64": base64.b64encode(path.read_bytes()).decode()}


def real_documents() -> list[IngestDocument]:
    record = json.loads((ROOT / "data/raw/unibridge/fetch_record.json").read_text(encoding="utf-8"))
    return [
        IngestDocument(
            source_id="ub",
            external_id=d["id"],
            title=d["title"],
            file=file_payload(ROOT / d["path"]),
            metadata={"office": d["office"], "type": d["type"], "author": d["publisher"], "date": d["fetched_at"][:10],
                      "project": "UniBridge", "source_url": d.get("landing") or d["source_url"]},
            access_level=AccessLevel.public,
            owner=OWNER[d["office"]],
            source_piece="P14",
        )
        for d in record["documents"]
    ]


def synthetic_documents() -> list[IngestDocument]:
    base = ROOT / "data" / "unibridge_synthetic"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    return [
        IngestDocument(
            source_id="ubsyn",
            external_id=d["id"],
            title=d["title"],
            file=file_payload(base / d["file"]),
            metadata={"office": d["office"], "type": d["type"], "author": "UniBridge prototype (synthetic)", "project": "UniBridge",
                      "source_url": f"data/unibridge_synthetic/{d['file']}"},
            access_level=AccessLevel(d["access_level"]),
            owner=d["owner"],
            source_piece="P14",
            synthetic=True,
            llm_generated=True,
        )
        for d in manifest["documents"]
    ]


def main() -> int:
    settings = unibridge_settings()
    t0 = time.perf_counter()
    services = build_services(settings)
    print(f"services ready in {time.perf_counter() - t0:.1f}s (collection {services.index.collection})")
    stats = {"ingested": 0, "unchanged": 0, "approved": 0, "passages": 0}
    for doc in real_documents() + synthetic_documents():
        owner = Principal(f"simulated-owner-{doc.metadata.office}", "officer", AccessLevel.restricted, (doc.metadata.office,))
        res = services.ingestion.ingest(doc, owner)
        stats["unchanged" if res.unchanged else "ingested"] += 1
        if res.status != "approved":
            t = time.perf_counter()
            res = services.ingestion.approve(res.document_id, owner, APPROVAL_NOTE, refresh_snapshot=False)
            stats["approved"] += 1
            print(f"approved {res.document_id:<52} {res.passages:>5} passages  {time.perf_counter() - t:5.1f}s")
        stats["passages"] += res.passages
    print(f"index snapshot: {services.store.refresh_snapshot_id()}")
    print(f"done: {stats} in {time.perf_counter() - t0:.1f}s; Qdrant points: {services.index.count()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
