"""Export and check the workflow net of the answer pipeline (src/p14_search/answer/flow.py).

Writes:
- docs/bpmn/answer_flow.pnml                         workflow net (PNML; opens in WoPeD)
- docs/images/answer_flow_net.png                    picture of the net
- eval/results/unibridge/answer_flow_soundness.json  soundness in code + pm4py (Woflan) on the PNML file,
                                                     and the end transition reached by every complete run

Usage:
    python scripts/build_answer_flow_model.py
"""

from __future__ import annotations

import json
import sys
import textwrap
from collections import Counter
from pathlib import Path

from build_scholarship_model import pnml

from p14_search.answer.flow import END_ANSWER, END_IDK, build_answer_net
from p14_search.procedure.model import SINK, SOURCE, Net
from p14_search.procedure.soundness import check_soundness, enabled, fire, pm4py_check

ROOT = Path(__file__).resolve().parents[1]
PNML = ROOT / "docs" / "bpmn" / "answer_flow.pnml"
PICTURE = ROOT / "docs" / "images" / "answer_flow_net.png"
RESULT = ROOT / "eval" / "results" / "unibridge" / "answer_flow_soundness.json"

# Picture only: position (column, row) and a short label for every node. The net itself is in answer/flow.py.
POSITION = {
    "i": (0, 0), "t_receive": (1, 0), "p_question": (2, 0), "t_language": (3, 0), "p_language": (4, 0), "t_retrieve": (5, 0),
    "p_first_ranking": (6, 0), "t_translate_fuse": (7, 0.8), "t_no_translation": (7, -0.8), "p_ranking": (8, 0),
    "t_sources": (9, 0), "p_sources": (10, 0),
    "t_llm_call": (11, 1), "p_llm_called": (12, 1), "t_llm_text": (13, 2), "p_generated": (14, 2), "t_verify": (15, 2),
    "p_verified": (16, 2), "t_kept": (17, 2), "t_skip_verifier": (17, 3.4), "t_all_dropped": (19.6, -1),
    "t_llm_failed": (13, 0), "t_verifier_llm_failed": (14, 0.5),
    "t_mode_extractive": (11, -1), "p_extractive": (14, -1), "t_extract": (15, -1), "p_extracted": (16, -1),
    "t_extracted_some": (17, 0), "t_extracted_none": (17, -2),
    "t_llm_no_answer": (13, -2.2), "t_insufficient": (11, -3),
    "p_answer": (18.5, 1), "t_respond": (20, 1),
    "p_no_answer": (18.5, -3), "t_idk": (20, -3), "p_idk": (21, -3), "t_no_handoff": (22, -2),
    "t_choose_office": (22, -4), "p_office": (23, -4), "t_draft": (24, -3.3), "t_out_of_scope": (24, -4.7),
    "o": (25.5, -1),
}
LABEL = {
    "t_receive": "receive question", "t_language": "detect language", "t_retrieve": "hybrid retrieval S2",
    "t_translate_fuse": "translate to Italian, retrieve again, RRF", "t_no_translation": "no translation",
    "t_sources": "load passages P1..Pk", "t_insufficient": "insufficient evidence", "t_mode_extractive": "extractive mode / no LLM",
    "t_llm_call": "LLM answer with citations", "t_llm_failed": "LLM failed", "t_llm_no_answer": "LLM: NO_ANSWER",
    "t_llm_text": "LLM: cited sentences", "t_verify": "verifier", "t_verifier_llm_failed": "LLM failed in support check",
    "t_skip_verifier": "mode 'llm': no verifier (evaluation only)", "t_kept": "sentences kept", "t_all_dropped": "all dropped",
    "t_extract": "extractive answer", "t_extracted_some": "sentences found", "t_extracted_none": "none found",
    "t_respond": "ANSWER with citations", "t_idk": "\"I don't know\"", "t_no_handoff": "no draft requested",
    "t_choose_office": "choose office", "t_draft": "HANDOFF e-mail draft", "t_out_of_scope": "no office: out of scope",
}
LANE_COLOUR = {"api": "#e7e6e1", "answer": "#cde2fb", "retrieval": "#c9eedd", "llm": "#fbdccb", "verifier": "#fbe6b3",
               "handoff": "#f6d3e0"}


def end_transitions(net: Net) -> dict:
    """Every maximal firing sequence from [i], grouped by its last transition (the net is acyclic)."""
    counts: Counter = Counter()
    stack = [(Counter({SOURCE: 1}), None)]
    while stack:
        marking, last = stack.pop()
        options = enabled(net, marking)
        if not options:
            assert +marking == Counter({SINK: 1}), f"run stops outside the final marking: {dict(marking)}"
            counts[last] += 1
        for tid in options:
            stack.append((fire(net, marking, tid), tid))
    runs = sum(counts.values())
    return {"complete_runs": runs, "runs_by_end_transition": dict(sorted(counts.items())),
            "runs_ending_in_answer_with_citations": counts[END_ANSWER],
            "runs_ending_in_i_dont_know": sum(counts[t] for t in END_IDK),
            "every_run_ends_in_answer_or_i_dont_know": runs == counts[END_ANSWER] + sum(counts[t] for t in END_IDK)}


def draw(net: Net) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Patch

    ink, muted, surface = "#0b0b0b", "#52514e", "#ffffff"
    half_w, half_h, radius = 0.44, 0.34, 0.2
    fig, ax = plt.subplots(figsize=(24, 9.2), facecolor=surface)
    ax.set_aspect("equal")
    ax.axis("off")
    def border(node: str, towards: str) -> tuple[float, float]:
        """Point where the segment node -> towards leaves the shape of `node` (circle or box)."""
        (x, y), (x2, y2) = POSITION[node], POSITION[towards]
        dx, dy = x2 - x, y2 - y
        length = (dx * dx + dy * dy) ** 0.5
        if node in net.places:
            scale = (radius + 0.03) / length
        else:
            scale = min((half_w + 0.03) / abs(dx) if dx else 9.0, (half_h + 0.03) / abs(dy) if dy else 9.0)
        return x + dx * scale, y + dy * scale

    for a, b in net.arcs:
        ax.add_patch(FancyArrowPatch(border(a, b), border(b, a), arrowstyle="-|>", mutation_scale=9, linewidth=0.8, color=muted,
                                     shrinkA=0, shrinkB=0, zorder=1))
    for p in net.places:
        x, y = POSITION[p]
        ax.add_patch(Circle((x, y), radius, facecolor=surface, edgecolor=ink, linewidth=1.6 if p in (SOURCE, SINK) else 1.0, zorder=2))
        if p == SOURCE:
            ax.add_patch(Circle((x, y), 0.07, color=ink, zorder=3))  # the token: one question
        ax.text(x, y - radius - 0.1, p, ha="center", va="top", fontsize=6.5, color=muted)
    for t in net.transitions.values():
        x, y = POSITION[t.id]
        ax.add_patch(FancyBboxPatch((x - half_w, y - half_h), 2 * half_w, 2 * half_h, boxstyle="round,pad=0,rounding_size=0.05",
                                    facecolor=LANE_COLOUR[t.lane], edgecolor=ink, linewidth=1.0, zorder=2))
        ax.text(x, y, textwrap.fill(LABEL[t.id], 15), ha="center", va="center", fontsize=6.6, color=ink, zorder=3, linespacing=1.05)
    ax.legend(handles=[Patch(facecolor=c, edgecolor=ink, label=lane) for lane, c in LANE_COLOUR.items()], title="transition = step of",
              loc="upper left", fontsize=8, title_fontsize=8, frameon=False, ncols=6)
    ax.set_title("Workflow net of the UniBridge answer pipeline (one token = one question; circles = places, boxes = transitions)",
                 loc="left", fontsize=12, color=ink, fontweight="bold")
    xs, ys = [p[0] for p in POSITION.values()], [p[1] for p in POSITION.values()]
    ax.set_xlim(min(xs) - 0.7, max(xs) + 0.7)
    ax.set_ylim(min(ys) - 0.8, max(ys) + 1.1)
    fig.tight_layout()
    PICTURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PICTURE, dpi=150, facecolor=surface)
    plt.close(fig)


def main() -> int:
    net = build_answer_net()
    assert set(POSITION) == set(net.places) | set(net.transitions) and set(LABEL) == set(net.transitions)
    PNML.write_text(pnml(net, "answer_flow", "UniBridge answer pipeline - workflow net"), encoding="utf-8", newline="\n")
    result = {
        "model": "src/p14_search/answer/flow.py", "pnml": "docs/bpmn/answer_flow.pnml",
        "places": len(net.places), "transitions": len(net.transitions), "arcs": len(net.arcs),
        "soundness_in_code": check_soundness(net),
        "pm4py_woflan_on_pnml": pm4py_check(str(PNML)),
        "runs": end_transitions(net),
    }
    RESULT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    draw(net)
    print(json.dumps({k: v for k, v in result.items() if k != "soundness_in_code"}, indent=1))
    print("sound (code):", result["soundness_in_code"]["sound"], "| reachable markings:", result["soundness_in_code"]["reachable_markings"])
    return 0 if result["soundness_in_code"]["sound"] and result["runs"]["every_run_ends_in_answer_or_i_dont_know"] else 1


if __name__ == "__main__":
    sys.exit(main())
