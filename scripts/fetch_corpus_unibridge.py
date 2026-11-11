"""Download the UniBridge corpus (real public documents for international students) listed in
data/unibridge_manifest.json.

- pdf: saved as served.
- html: only the content region of the page (manifest `selector`) is kept; FAQ questions written as a bold
  first line of a paragraph become <h3> headings, so each answer is its own section (citations point to the
  question). The SHA-256 of the original response and of the derived file are both recorded.
- urn: Normattiva consolidated export, reusing scripts/fetch_corpus.py.

Usage:
    python scripts/fetch_corpus_unibridge.py            # download missing files only
    python scripts/fetch_corpus_unibridge.py --force    # re-download everything

Output: data/raw/unibridge/<id>.<pdf|html> and data/raw/unibridge/fetch_record.json (not committed).
A document that cannot be downloaded is reported and skipped (see docs/OPEN_QUESTIONS.md).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_corpus  # noqa: E402  (Normattiva helpers)

MANIFEST = ROOT / "data" / "unibridge_manifest.json"
OUT_DIR = ROOT / "data" / "raw" / "unibridge"
USER_AGENT = "unibridge/0.1 (university project, UNICAM; polite crawler)"
DELAY_S = 1.5


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _is_question(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    upper = letters and sum(c.isupper() for c in letters) / len(letters) > 0.8
    return 8 <= len(text) <= 250 and (text.endswith("?") or bool(upper))


def content_html(page: bytes, selector: str, title: str, url: str) -> bytes:
    """Content region of a page as a small standalone HTML document."""
    soup = BeautifulSoup(page.decode("utf-8", errors="replace"), "html.parser")
    region = soup.select_one(selector)
    if region is None:
        raise RuntimeError(f"selector {selector!r} not found")
    for tag in region(["script", "style", "noscript", "nav", "form", "iframe", "img", "svg"]):
        tag.decompose()
    for p in region.find_all("p"):
        first = next((c for c in p.children if not (isinstance(c, NavigableString) and not c.strip())), None)
        if isinstance(first, Tag) and first.name in ("strong", "b"):
            q = re.sub(r"\s+", " ", first.get_text(" ", strip=True).replace("\xa0", " ")).strip()
            if _is_question(q):
                h = soup.new_tag("h3")
                h.string = q
                p.insert_before(h)
                first.decompose()
    doc = (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title><meta name=\"source\" content=\"{url}\"></head>\n<body>\n<h1>{title}</h1>\n"
        f"{region}\n</body></html>\n"
    )
    return doc.encode("utf-8")


def fetch(doc: dict, force: bool) -> dict:
    target = OUT_DIR / f"{doc['id']}.{doc['format']}"
    record = {k: v for k, v in doc.items()}
    record["path"] = str(target.relative_to(ROOT)).replace("\\", "/")
    if target.exists() and not force:
        record["skipped"] = True
        return record
    if "urn" in doc:
        fetch_corpus.OUT_DIR = OUT_DIR
        act = fetch_corpus.fetch_act({"id": doc["id"], "urn": doc["urn"], "format": doc["format"]}, force=True)
        record.update(source_url=act["source_url"], url=act["urn_url"], original_sha256=act["sha256"])
        data = target.read_bytes()
    else:
        raw = get(doc["url"])
        record["original_sha256"] = hashlib.sha256(raw).hexdigest()
        record["source_url"] = doc["url"]
        if doc["format"] == "pdf":
            if not raw.startswith(b"%PDF"):
                raise RuntimeError("response is not a PDF")
            data = raw
        else:
            data = content_html(raw, doc["selector"], doc["title"], doc["url"])
            record["derived"] = f"content region {doc['selector']!r}; FAQ questions as <h3> (scripts/fetch_corpus_unibridge.py)"
        target.write_bytes(data)
    record["sha256"] = hashlib.sha256(data).hexdigest()
    record["bytes"] = len(data)
    record["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    record_path = OUT_DIR / "fetch_record.json"
    previous = {}
    if record_path.exists():
        previous = {r["id"]: r for r in json.loads(record_path.read_text(encoding="utf-8"))["documents"]}
    docs = json.loads(MANIFEST.read_text(encoding="utf-8"))["documents"]
    records, failures = [], []
    for doc in docs:
        try:
            rec = fetch(doc, args.force)
        except Exception as exc:  # report and continue with the other documents
            failures.append({"id": doc["id"], "url": doc.get("url") or doc.get("urn"), "error": str(exc)})
            print(f"FAIL {doc['id']}: {exc}", file=sys.stderr)
            continue
        if rec.pop("skipped", False):
            rec = previous.get(doc["id"], rec)
            print(f"skip {doc['id']} (exists)")
        else:
            print(f"ok   {doc['id']:<46} {rec['bytes']:>9} B")
            time.sleep(DELAY_S)
        records.append(rec)
    record_path.write_text(json.dumps({"documents": records, "failures": failures}, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"{len(records)} documents recorded, {len(failures)} failures -> {record_path.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
