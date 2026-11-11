"""Build the web presentation of UniBridge from deliverables/build/presentation_template.html.

Numbers come from eval/results/unibridge/*.json; diagrams and screenshots are embedded as data URIs, so the output is
one self-contained file that opens offline (arrow keys or the control bar to move, sections in the drop-down).

Usage:
    python scripts/build_web_presentation.py
Outputs: deliverables/UniBridge_Presentation.html (complete document) and, with --fragment PATH, the same page
without the document skeleton (for hosts that add their own).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

from p14_search.i18n import HAND_WRITTEN, LANGS

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "eval" / "results" / "unibridge"
TEMPLATE = ROOT / "deliverables" / "build" / "presentation_template.html"
OUT = ROOT / "deliverables" / "UniBridge_Presentation.html"


def load(name: str) -> dict:
    return json.loads((RES / name).read_text(encoding="utf-8"))


def data_uri(path: Path, crop: tuple[int, int, int, int] | None = None, width: int = 1500, png: bool = False) -> str:
    im = Image.open(path).convert("RGBA" if png else "RGB")
    if crop:
        im = im.crop(crop)
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    if png:  # keeps transparency (the logo on the dark theme)
        im.save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    im.save(buf, "JPEG", quality=86, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def pct(x: float, d: int = 0) -> str:
    return f"{x * 100:.{d}f}%"


def build() -> str:
    ev, tr, ans, ml = load("eval_latest.json"), load("translation_latest.json"), load("answers_latest.json"), load("multilingual_latest.json")
    sound, proc, hand, cost, corpus = (load("procedure_soundness.json"), load("procedure_eval.json"), load("handoff_eval.json"),
                                       load("llm_cost.json"), load("corpus_stats.json"))
    cf = ans["configs"]
    rows = [
        ("Answered (not \"I don't know\")", lambda c: f"{c['answered']} of {c['n']}"),
        ("Citation precision", lambda c: f"{c['citation_precision']:.2f}"),
        ("Sentences without a valid citation", lambda c: pct(c["uncited_sentence_rate"])),
        ("Answer in the language of the question", lambda c: pct(c["answer_language_correct"])),
        ("\"I don't know\" on out-of-scope questions", lambda c: pct(c["idk_correct_oos"])),
        ("LLM calls per answer", lambda c: f"{c['llm_calls_per_answer']}"),
        ("Cost per answer (USD)", lambda c: "0" if not c["cost_usd_per_answer"] else f"{c['cost_usd_per_answer']:.5f}"),
        ("Latency, median (ms)", lambda c: f"{c['latency_ms_p50']:,.0f}"),
    ]
    answer_rows = "\n".join(
        f"<tr><td><b>{label}</b></td>" + "".join(f'<td class="n{" hi" if k == "llm_verified" else ""}">{fn(cf[k])}</td>'
                                                  for k in ("extractive", "llm", "llm_verified")) + "</tr>"
        for label, fn in rows)
    nl = ml["new_languages"]
    langs = ml["languages"]
    chart = {
        "c1": {"groups": ["Italian", "English", "Arabic"], **{s: [ev["by_lang"][l][s]["ndcg@10"] for l in ("it", "en", "ar")] for s in ("B0", "S1", "S2")}},
        "c2": {"groups": ["English", "Arabic"], **{s: [tr["by_lang"][l][s]["ndcg@10"] for l in ("en", "ar")] for s in ("S2", "S3", "S3f")}},
        "c3": {"groups": langs, **{s: [ml["by_lang"][l]["retrieval"][s]["ndcg@10"] for l in langs] for s in ("S2", "S3f")}},
    }
    ev_shots = ROOT / "docs" / "evidence" / "unibridge"
    values = {
        "__LOGO__": data_uri(ROOT / "docs" / "images" / "unicam_logo.png", width=220, png=True),
        "__COMPONENTS__": data_uri(ROOT / "docs" / "images" / "ub-02-components.png", width=1700),
        "__BPMN__": data_uri(ROOT / "docs" / "images" / "scholarship_bpmn.png", width=2200),
        "__GUIDE__": data_uri(ev_shots / "ub_07_scholarship_guide.png", crop=(330, 665, 1440, 1700), width=1100),
        "__HANDOFF__": data_uri(ev_shots / "ub_04_role_visitor.png", crop=(300, 200, 1440, 1060), width=1140),
        "__ANSWER_FR__": data_uri(ev_shots / "ub_08_answer_fr.png", crop=(330, 200, 1440, 700), width=1110),
        "__LANGS__": str(len(LANGS)),
        "__MARKINGS__": str(sound["soundness_in_code"]["reachable_markings"]),
        "__NODES__": str(sound["bpmn"]["nodes"]), "__PLACES__": str(sound["places"]), "__TRANS__": str(sound["transitions"]),
        "__SCEN__": str(proc["scenarios_fully_correct"]),
        "__DOCS__": str(corpus["totals"]["documents"]), "__DOCS_REAL__": str(corpus["source"]["ub"]["documents"]),
        "__DOCS_SYN__": str(corpus["source"]["ubsyn"]["documents"]), "__PASSAGES__": f"{corpus['totals']['passages']:,}",
        "__TEST__": str(ev["n_test_queries"]), "__IT__": str(ev["n_by_lang"]["it"]), "__EN__": str(ev["n_by_lang"]["en"]),
        "__AR__": str(ev["n_by_lang"]["ar"]), "__ML_N__": str(ml["n_new_language_questions"]),
        "__BM25_AR__": pct(ev["hypothesis_bm25_arabic"]["B0_no_relevant_in_top10_share_ar"]),
        "__N_AR__": str(ev["hypothesis_bm25_arabic"]["n_arabic_in_scope_test"]),
        "__ACL__": f"{ev['acl_leakage']['passages_checked']:,}",
        "__S2_ALL__": f"{tr['overall']['S2']['ndcg@10']:.2f}", "__S3F_ALL__": f"{tr['overall']['S3f']['ndcg@10']:.2f}",
        "__P_FUSE__": str(tr["randomization_tests"]["S3f_vs_S2_ndcg@10_all"]["p_value"]),
        "__ML_DETECT__": pct(nl["detection_accuracy"], 1), "__ML_LANG__": pct(nl["answer_language_correct"], 1),
        "__ML_FA_S2__": pct(nl["retrieval"]["S2"]["false_abstention_rate"]), "__ML_FA_S3F__": pct(nl["retrieval"]["S3f"]["false_abstention_rate"]),
        "__ML_P__": str(ml["randomization_tests"]["S3f_vs_S2_ndcg@10_new_languages"]["p_value"]),
        "__ML_CIT__": f"{nl['citation_precision']:.2f}", "__ML_LANGS_N__": str(len(LANGS) - len(HAND_WRITTEN)),
        "__ANSWER_ROWS__": answer_rows,
        "__HAND__": pct(hand["in_scope_office_accuracy"]),
        "__COST__": f"{cost['estimated_cost_usd']:.2f}", "__COST_ANS__": f"{cf['llm_verified']['cost_usd_per_answer']:.5f}",
        "__CHART_DATA__": json.dumps(chart),
    }
    html = TEMPLATE.read_text(encoding="utf-8")
    for k, v in values.items():
        html = html.replace(k, v)
    left = [w for w in ("__",) if f"{w}LOGO" in html or "__ML_" in html or "__CHART" in html]
    if left:
        raise SystemExit("unfilled placeholders in the template")
    return html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fragment", default=None, help="also write the page without <!doctype>/<html>/<head>/<body>")
    args = parser.parse_args()
    page = build()
    OUT.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                   '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                   "</head>\n<body>\n" + page + "\n</body>\n</html>\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()} ({OUT.stat().st_size // 1024} KB)")
    if args.fragment:
        Path(args.fragment).write_text(page, encoding="utf-8", newline="\n")
        print(f"wrote {args.fragment}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
