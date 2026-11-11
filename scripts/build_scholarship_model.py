"""Export the scholarship procedure model (src/p14_search/procedure/model.py) and check it.

Writes:
- docs/bpmn/scholarship.bpmn   BPMN 2.0 with diagram (opens in bpmn.io / Camunda Modeler)
- docs/bpmn/scholarship.pnml   workflow net (PNML, place/transition net; opens in WoPeD)
- eval/results/unibridge/procedure_soundness.json   soundness in code + pm4py (Woflan) on the PNML file

Usage:
    python scripts/build_scholarship_model.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from p14_search.procedure.model import SINK, SOURCE, build_net
from p14_search.procedure.soundness import check_soundness, pm4py_check

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "bpmn"
RESULT = ROOT / "eval" / "results" / "unibridge" / "procedure_soundness.json"

# --- BPMN ----------------------------------------------------------------------------------------
# (id, type, name, lane, x, y) - x, y = top-left corner. Tasks 100x60, gateways 50x50, events 36x36.
SIZE = {"task": (100, 60), "userTask": (100, 60), "startEvent": (36, 36), "endEvent": (36, 36),
        "exclusiveGateway": (50, 50), "parallelGateway": (50, 50)}
NODES = [
    ("start", "startEvent", "Call for applications 2026/2027 published (Art. 1)", "erdis", 82, 357),
    ("g_and_split", "parallelGateway", "", "student", 160, 100),
    ("g_econ_split", "exclusiveGateway", "Family income in Italy?", "student", 250, 50),
    ("t_dsu", "userTask", "Sign DSU, obtain ISEE for university study (Art. 8)", "student", 340, 10),
    ("t_parificato", "userTask", "Submit legalised documents for ISEE parificato by 28/8/2026 (Art. 8.8, 11)", "student", 340, 95),
    ("g_econ_merge", "exclusiveGateway", "", "student", 480, 50),
    ("t_apply", "userTask", "Submit and confirm online application by 28/8/2026 (Art. 10)", "student", 560, 45),
    ("t_enrol", "userTask", "Enrol at the university (Art. 3)", "student", 340, 170),
    ("g_and_join", "parallelGateway", "Applications closed", "erdis", 700, 350),
    ("t_check", "task", "Check merit and economic requirements (Art. 7, 8, 14)", "erdis", 790, 345),
    ("t_provisional", "task", "Publish provisional ranking, ~15/9/2026 (Art. 15.1)", "erdis", 930, 345),
    ("g_review_split", "exclusiveGateway", "Request for review?", "erdis", 1070, 350),
    ("t_review_request", "userTask", "Submit request for review within 5 days (Art. 15.2)", "student", 1150, 95),
    ("t_review_decision", "task", "Decide on the request for review (Art. 15.2)", "erdis", 1290, 290),
    ("g_review_merge", "exclusiveGateway", "", "erdis", 1430, 350),
    ("t_final", "task", "Publish final ranking, first half of October 2026 (Art. 15.3)", "erdis", 1510, 345),
    ("g_outcome", "exclusiveGateway", "Awarded?", "erdis", 1650, 350),
    ("end_not_awarded", "endEvent", "Not awarded or excluded (Art. 20)", "erdis", 1757, 445),
    ("t_pay_first", "task", "Pay first instalment(s) (Art. 17.3)", "erdis", 1740, 345),
    ("g_merit", "exclusiveGateway", "Merit for the balance?", "erdis", 1880, 350),
    ("t_pay_balance", "task", "Pay the balance (Art. 17.3)", "erdis", 1970, 290),
    ("end_completed", "endEvent", "Scholarship paid", "erdis", 2117, 302),
    ("t_revoke", "task", "Revoke and recover amounts (Art. 21)", "erdis", 1970, 400),
    ("end_revoked", "endEvent", "Scholarship revoked", "erdis", 2117, 412),
]
FLOWS = [
    ("start", "g_and_split", ""), ("g_and_split", "g_econ_split", ""), ("g_and_split", "t_enrol", ""),
    ("g_econ_split", "t_dsu", "yes"), ("g_econ_split", "t_parificato", "no (family abroad)"),
    ("t_dsu", "g_econ_merge", ""), ("t_parificato", "g_econ_merge", ""), ("g_econ_merge", "t_apply", ""),
    ("t_apply", "g_and_join", ""), ("t_enrol", "g_and_join", ""), ("g_and_join", "t_check", ""),
    ("t_check", "t_provisional", ""), ("t_provisional", "g_review_split", ""),
    ("g_review_split", "t_review_request", "yes"), ("t_review_request", "t_review_decision", ""),
    ("t_review_decision", "g_review_merge", ""), ("g_review_split", "g_review_merge", "no"),
    ("g_review_merge", "t_final", ""), ("t_final", "g_outcome", ""),
    ("g_outcome", "end_not_awarded", "no"), ("g_outcome", "t_pay_first", "yes"),
    ("t_pay_first", "g_merit", ""), ("g_merit", "t_pay_balance", "met"), ("g_merit", "t_revoke", "not met by 30/11/2027"),
    ("t_pay_balance", "end_completed", ""), ("t_revoke", "end_revoked", ""),
]
LANES = {"student": ("Student", 0, 240), "erdis": ("ERDIS Marche", 240, 300)}
POOL_X, POOL_W = 30, 2170
# BPMN element <-> workflow-net transition (shown in docs/PROCEDURE.md and checked by tests)
BPMN_TO_NET = {
    "start": "t_call", "g_and_split": "t_split", "t_dsu": "t_dsu", "t_parificato": "t_parificato", "t_apply": "t_apply",
    "t_enrol": "t_enrol", "g_and_join": "t_join", "t_check": "t_check", "t_provisional": "t_provisional",
    "t_review_request": "t_review_request", "t_review_decision": "t_review_decision", "t_final": "t_final",
    "end_not_awarded": "t_not_awarded", "t_pay_first": "t_pay_first", "t_pay_balance": "t_pay_balance", "t_revoke": "t_revoke",
}


def bpmn() -> str:
    node = {n[0]: n for n in NODES}
    flows = [(f"f{i + 1}", s, t, name) for i, (s, t, name) in enumerate(FLOWS)]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"'
           ' xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI"'
           ' id="defs_scholarship" targetNamespace="https://unibridge.example/bpmn" exporter="scripts/build_scholarship_model.py">',
           '  <collaboration id="collab">',
           '    <participant id="pool" name="ERDIS scholarship procedure a.y. 2026/2027" processRef="scholarship"/>',
           '  </collaboration>',
           '  <process id="scholarship" name="ERDIS scholarship 2026/2027" isExecutable="false">',
           '    <laneSet id="lanes">']
    for lid, (lname, _, _) in LANES.items():
        out.append(f'      <lane id="lane_{lid}" name="{lname}">')
        out += [f"        <flowNodeRef>{n[0]}</flowNodeRef>" for n in NODES if n[3] == lid]
        out.append("      </lane>")
    out.append("    </laneSet>")
    for nid, typ, name, *_ in NODES:
        inc = [f for f in flows if f[2] == nid]
        outg = [f for f in flows if f[1] == nid]
        out.append(f'    <{typ} id="{nid}" name="{escape(name, {chr(34): "&quot;"})}">')
        out += [f"      <incoming>{f[0]}</incoming>" for f in inc] + [f"      <outgoing>{f[0]}</outgoing>" for f in outg]
        out.append(f"    </{typ}>")
    for fid, s, t, name in flows:
        out.append(f'    <sequenceFlow id="{fid}" sourceRef="{s}" targetRef="{t}"' + (f' name="{escape(name)}"' if name else "") + "/>")
    out += ["  </process>", '  <bpmndi:BPMNDiagram id="diagram">', '    <bpmndi:BPMNPlane id="plane" bpmnElement="collab">',
            f'      <bpmndi:BPMNShape id="pool_di" bpmnElement="pool" isHorizontal="true"><dc:Bounds x="{POOL_X}" y="0" width="{POOL_W}" height="540"/></bpmndi:BPMNShape>']
    for lid, (_, y, h) in LANES.items():
        out.append(f'      <bpmndi:BPMNShape id="lane_{lid}_di" bpmnElement="lane_{lid}" isHorizontal="true">'
                   f'<dc:Bounds x="{POOL_X + 30}" y="{y}" width="{POOL_W - 30}" height="{h}"/></bpmndi:BPMNShape>')
    for nid, typ, _, _, x, y in NODES:
        w, h = SIZE[typ]
        marker = ' isMarkerVisible="true"' if typ == "exclusiveGateway" else ""
        out.append(f'      <bpmndi:BPMNShape id="{nid}_di" bpmnElement="{nid}"{marker}><dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}"/></bpmndi:BPMNShape>')
    for fid, s, t, _ in flows:
        (_, ts, _, _, sx, sy), (_, tt, _, _, tx, ty) = node[s], node[t]
        sw, sh = SIZE[ts]
        tw, th = SIZE[tt]
        out.append(f'      <bpmndi:BPMNEdge id="{fid}_di" bpmnElement="{fid}"><di:waypoint x="{sx + sw}" y="{sy + sh // 2}"/>'
                   f'<di:waypoint x="{tx}" y="{ty + th // 2}"/></bpmndi:BPMNEdge>')
    out += ["    </bpmndi:BPMNPlane>", "  </bpmndi:BPMNDiagram>", "</definitions>", ""]
    return "\n".join(out)


# --- PNML ----------------------------------------------------------------------------------------
def layout(net) -> dict[str, tuple[int, int]]:
    """x = longest distance from i (in nodes), y = order within that column."""
    succ: dict[str, list[str]] = {}
    for a, b in net.arcs:
        succ.setdefault(a, []).append(b)
    level = {SOURCE: 0}
    changed = True
    while changed:
        changed = False
        for a, bs in succ.items():
            for b in bs:
                if a in level and level.get(b, -1) < level[a] + 1:
                    level[b] = level[a] + 1
                    changed = True
    level[SINK] = max(level.values()) + 1
    columns: dict[int, list[str]] = {}
    for n in [*net.places, *net.transitions]:
        columns.setdefault(level[n], []).append(n)
    return {n: (60 + 110 * lv, 80 + 110 * i) for lv, ns in columns.items() for i, n in enumerate(ns)}


def pnml(net) -> str:
    pos = layout(net)
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<pnml>",
           '  <net id="scholarship" type="http://www.informatik.hu-berlin.de/top/pntd/ptNetb">',
           "    <name><text>ERDIS scholarship 2026/2027 - workflow net</text></name>"]
    for p in net.places:
        x, y = pos[p]
        out.append(f'    <place id="{p}"><name><text>{p}</text><graphics><offset x="0" y="40"/></graphics></name>'
                   f'<graphics><position x="{x}" y="{y}"/><dimension x="40" y="40"/></graphics>'
                   + ("<initialMarking><text>1</text></initialMarking>" if p == SOURCE else "") + "</place>")
    for t in net.transitions.values():
        x, y = pos[t.id]
        out.append(f'    <transition id="{t.id}"><name><text>{escape(t.name)}</text><graphics><offset x="0" y="40"/></graphics></name>'
                   f'<graphics><position x="{x}" y="{y}"/><dimension x="40" y="40"/></graphics></transition>')
    for i, (a, b) in enumerate(net.arcs):
        out.append(f'    <arc id="a{i + 1}" source="{a}" target="{b}"><inscription><text>1</text></inscription></arc>')
    out += ["  </net>", "</pnml>", ""]
    return "\n".join(out)


def main() -> int:
    net = build_net()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scholarship.bpmn").write_text(bpmn(), encoding="utf-8", newline="\n")
    pnml_path = OUT / "scholarship.pnml"
    pnml_path.write_text(pnml(net), encoding="utf-8", newline="\n")
    result = {
        "model": "src/p14_search/procedure/model.py",
        "places": len(net.places), "transitions": len(net.transitions), "arcs": len(net.arcs),
        "bpmn": {"nodes": len(NODES), "flows": len(FLOWS), "file": "docs/bpmn/scholarship.bpmn"},
        "soundness_in_code": check_soundness(net),
        "pm4py_woflan_on_pnml": pm4py_check(str(pnml_path)),
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "soundness_in_code"}, indent=1))
    print("sound (code):", result["soundness_in_code"]["sound"], "| reachable markings:", result["soundness_in_code"]["reachable_markings"])
    return 0 if result["soundness_in_code"]["sound"] else 1


if __name__ == "__main__":
    sys.exit(main())
