"""Scholarship procedure: workflow-net soundness, BPMN/PNML export, guide rules, state machine, .ics, API."""

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from p14_search.models import ProcedureRequest
from p14_search.procedure.guide import ScholarshipGuide
from p14_search.procedure.ics import calendar
from p14_search.procedure.model import STEPS, Net, build_net
from p14_search.procedure.soundness import check_soundness, enabled

BASE = dict(today="2026-11-11", level="L", year=2, credits=30, isee=18000, ispe=30000, application_submitted=True)


def test_scholarship_net_is_a_sound_workflow_net():
    result = check_soundness(build_net())
    assert result["workflow_net"]["ok"] and result["bounded"]
    assert result["option_to_complete"] and result["proper_completion"] and result["no_dead_transitions"]
    assert result["sound"]


def test_soundness_check_detects_a_deadlock_and_a_dead_transition():
    # without "decide on the request for review" a student who asks for a review is stuck in p_review
    broken = build_net()
    del broken.transitions["t_review_decision"]
    result = check_soundness(broken)
    assert not result["sound"] and not result["option_to_complete"]
    assert {"p_review": 1} in result["markings_that_cannot_complete"]
    # an AND-join waiting for a place that is never marked -> stuck markings and dead transitions
    steps = {s.id: s for s in STEPS}
    steps["t_join"] = replace(steps["t_join"], inputs=("p_applied", "p_enrolled", "p_never"))
    places = build_net().places + ["p_never"]
    result = check_soundness(Net(places, steps))
    assert not result["sound"] and not result["option_to_complete"] and "t_check" in result["dead_transitions"]


def test_exported_bpmn_and_pnml_match_the_model():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import build_scholarship_model as exporter

    bpmn = ET.fromstring(exporter.bpmn())
    ns = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
    ids = {e.get("id") for e in bpmn.iter() if e.get("id")}
    assert {"start", "g_and_split", "t_apply", "g_outcome", "end_completed"} <= ids
    assert len(bpmn.findall(".//b:sequenceFlow", ns)) == len(exporter.FLOWS)
    net = build_net()
    assert set(exporter.BPMN_TO_NET.values()) <= set(net.transitions)
    pnml = ET.fromstring(exporter.pnml(net))
    assert len(pnml.findall(".//place")) == len(net.places) and len(pnml.findall(".//transition")) == len(net.transitions)
    assert len(pnml.findall(".//arc")) == len(net.arcs)


@pytest.fixture(scope="module")
def guide():
    return ScholarshipGuide(None)  # no store: citations without passage ids


def test_rules_use_thresholds_of_the_call(guide):
    ok = guide.guide(ProcedureRequest(**BASE), "t")
    assert ok.verdict == "eligible" and {r.id: r.outcome for r in ok.rules}["merit"] == "pass"
    assert guide.guide(ProcedureRequest(**{**BASE, "isee": 24000.01}), "t").verdict == "not_eligible"
    assert guide.guide(ProcedureRequest(**{**BASE, "isee": 24000}), "t").verdict == "eligible"  # "fino a" = at most
    assert guide.guide(ProcedureRequest(**{**BASE, "credits": 24}), "t").verdict == "not_eligible"
    capped = guide.guide(ProcedureRequest(**{**BASE, "credits": 18, "bonus_credits": 10}), "t")
    assert "bonus capped at 5" in next(r.detail for r in capped.rules if r.id == "merit")
    for r in ok.rules:
        assert r.citation.section and r.citation.quote


def test_state_machine_only_fires_enabled_transitions(guide):
    early = guide.guide(ProcedureRequest(**{**BASE, "today": "2026-09-01"}), "t")
    assert early.status.marking == ["p_checked"] and [s.id for s in early.status.next] == ["t_provisional"]
    net = guide.net
    m = Counter({p: 1 for p in early.status.marking})
    assert [t for t in enabled(net, m)] == ["t_provisional"]
    late = guide.guide(ProcedureRequest(**{**BASE, "credits": 10}), "t")
    assert late.status.finished and late.status.marking == ["o"] and late.status.done[-1].id == "t_not_awarded"


def test_checklist_and_ics(guide):
    r = guide.guide(ProcedureRequest(**{**BASE, "family_abroad": True, "non_eu": True, "year": 1, "credits": None,
                                         "language": "ar"}), "t")
    ids = [c.id for c in r.checklist]
    assert "parificato" in ids and "permit" in ids and "credits_first_year" in ids and "isee" not in ids
    assert any("؀" <= ch <= "ۿ" for ch in r.checklist[0].text)
    assert r.ics.startswith("BEGIN:VCALENDAR\r\n") and r.ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20260828" in r.ics and r.ics.count("BEGIN:VEVENT") == len(r.deadlines)
    assert all(len(line.encode()) <= 75 for line in r.ics.split("\r\n"))


def test_ics_escapes_and_folds():
    ics = calendar([("2026-08-28", "A, b; c", "x" * 200)], __import__("datetime").date(2026, 1, 1))
    assert "SUMMARY:A\\, b\\; c" in ics and "\r\n " in ics


def test_procedure_endpoint(client):
    r = client.post("/v1/procedure/scholarship", json={**BASE, "language": "it"}, headers={"X-API-Key": "key-public"})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "eligible" and body["verdict_text"].startswith("In base")
    assert client.post("/v1/procedure/scholarship", json={**BASE, "year": 9}, headers={"X-API-Key": "key-public"}).status_code == 422


def test_procedure_facts_are_not_logged_or_sent_to_an_llm(client, services):
    import logging

    from p14_search.observability.logging import JsonFormatter

    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(JsonFormatter().format(record))
    logging.getLogger().addHandler(handler)
    try:
        client.post("/v1/procedure/scholarship", json={**BASE, "isee": 12345.67}, headers={"X-API-Key": "key-public"})
    finally:
        logging.getLogger().removeHandler(handler)
    logs = " ".join(records)
    assert "procedure guide" in logs and "12345" not in logs
    assert services.llm is None  # the guide has no LLM dependency at all
    rows = services.store.query("SELECT query FROM query_log")
    assert all("12345" not in r["query"] for r in rows)
