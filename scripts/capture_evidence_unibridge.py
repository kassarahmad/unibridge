"""Collect evidence that the UniBridge demo runs on this machine -> docs/evidence/unibridge/

- screenshots of the Streamlit UI (Playwright driving the locally installed Microsoft Edge): answers in three
  languages with citations, role-dependent answers, "I don't know" + office e-mail draft, scholarship guide;
- raw API outputs of the same questions (api_session.txt).
Read-only: nothing is ingested, no e-mail is sent. Answers may call the configured LLM (cached on disk).

Usage (UniBridge API on :8001 and the UI on :8502 running):
    uvicorn p14_search.unibridge_main:app --port 8001
    streamlit run frontend/unibridge_app.py --server.port 8502 --server.headless true
    python scripts/capture_evidence_unibridge.py [--api http://127.0.0.1:8001] [--ui http://127.0.0.1:8502]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "unibridge"

# (role, UI language, question, screenshot, open the sources expander, ask for an e-mail draft)
CASES = [
    ("visitor", "en", "How much is the ERDIS scholarship for a student living away from home?", "ub_01_answer_en.png", True, False),
    ("visitor", "ar", "ما هو الموعد النهائي لتقديم طلب المنحة الدراسية؟", "ub_02_answer_ar.png", True, False),
    ("visitor", "it", "Entro quando devo pagare le tasse universitarie?", "ub_03_answer_it_draft.png", True, True),
    ("visitor", "en", "Is there a buddy programme for international students?", "ub_04_role_visitor.png", False, False),
    ("student", "en", "Is there a buddy programme for international students?", "ub_05_role_student.png", True, False),
    ("visitor", "en", "Which football team won the Italian league last year?", "ub_06_out_of_scope.png", False, False),
]


def api_session(api: str, keys: dict[str, str]) -> None:
    lines = [f"Captured {dt.datetime.now().isoformat(timespec='seconds')} against {api}", ""]
    with httpx.Client(base_url=api, timeout=180) as c:
        lines += ["GET /v1/health", json.dumps(c.get("/v1/health").json(), indent=2), ""]
        for role, _, q, *_ in CASES:
            r = c.post("/v1/answer", json={"query": q}, headers={"X-API-Key": keys[role]})
            b = r.json()
            lines.append(f"POST /v1/answer  role={role}  query={q!r}  -> HTTP {r.status_code}, request_id={b['request_id']}")
            lines.append(f"  language={b['language']}  mode={b['mode']}  insufficient_evidence={b['insufficient_evidence']}"
                         f"  query_italian={b.get('query_italian')!r}  latency_ms={b['latency_ms']}")
            if b.get("llm"):
                u = b["llm"]
                lines.append(f"  llm={u['provider']}:{u['model']} calls={u['calls']} cached={u['cached_calls']} cost_usd={u['cost_usd']}")
            for s in b["sentences"]:
                lines.append(f"  - {s['text']}  {s['passage_ids']}")
            if b.get("handoff") and b["handoff"].get("draft"):
                d = b["handoff"]["draft"]
                lines.append(f"  handoff -> {d['office_id']}: {d['subject']}")
            lines.append("")
    (OUT / "api_session.txt").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("wrote docs/evidence/unibridge/api_session.txt")


def screenshots(ui: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2200}, device_scale_factor=1)

        def setup(role: str, lang: str, path: str = "") -> None:
            page.goto(f"{ui}/{path}", wait_until="networkidle")
            page.get_by_test_id("stSidebar").wait_for(timeout=60000)
            page.get_by_test_id("stSidebar").get_by_role("radio", name={"it": "Italiano", "en": "English", "ar": "العربية"}[lang]).click()
            page.wait_for_timeout(800)
            if role != "visitor":
                page.get_by_test_id("stSidebar").locator('[data-testid="stSelectbox"]').first.click()
                page.get_by_role("option", name=role, exact=True).click()
                page.wait_for_timeout(800)

        for role, lang, q, shot, expand, draft in CASES:
            setup(role, lang)
            box = page.get_by_test_id("stChatInputTextArea")
            box.fill(q)
            box.press("Enter")
            page.locator('[data-testid="stChatMessage"]').nth(1).wait_for(timeout=180000)
            page.wait_for_timeout(1500)
            if expand:
                page.locator('[data-testid="stExpander"] summary').first.click()
                page.wait_for_timeout(800)
            if draft:
                page.get_by_role("button", name={"it": "Prepara una e-mail all'ufficio", "en": "Draft an e-mail to the office", "ar": "أعدّ رسالة إلى المكتب"}[lang]).click()
                page.locator('[data-testid="stTextArea"]').first.wait_for(timeout=120000)
                page.wait_for_timeout(1000)
            page.screenshot(path=str(OUT / shot), full_page=True)
            print("wrote docs/evidence/unibridge/" + shot)

        # A second-year bachelor student before the deadline (fictional data, the guide stores nothing).
        setup("visitor", "en", "scholarship_guide")
        for part, value in (("month", "08"), ("day", "01")):  # date segments (react-aria spinbuttons)
            seg = page.get_by_role("spinbutton", name=f"{part}, Reference date")
            seg.click()
            seg.press_sequentially(value)
        isee = page.get_by_label("ISEE for university study (EUR, 0 = not known)", exact=True)
        isee.fill("15000")
        isee.press("Tab")
        page.get_by_role("button", name="Check").click()
        page.get_by_text("Your checklist").wait_for(timeout=60000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "ub_07_scholarship_guide.png"), full_page=True)
        print("wrote docs/evidence/unibridge/ub_07_scholarship_guide.png")
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    parser.add_argument("--ui", default="http://127.0.0.1:8502")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    cfg = json.loads((ROOT / "config" / "principals_unibridge.json").read_text(encoding="utf-8"))["principals"]
    keys = {p["name"]: env[p["api_key_env"]] for p in cfg}
    api_session(args.api, keys)
    screenshots(args.ui)
    return 0


if __name__ == "__main__":
    sys.exit(main())
