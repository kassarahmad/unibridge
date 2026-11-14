"""Workflow net of the answer pipeline: soundness, export, and agreement with the real service (API responses
are replayed on the net). The LLM is a FakeProvider."""

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from conftest import CORPUS, PRINCIPALS, ingest_payload
from p14_search.answer.flow import END_ANSWER, END_IDK, STEPS, build_answer_net
from p14_search.answer.llm import FakeProvider
from p14_search.api.app import create_app
from p14_search.config import Settings
from p14_search.indexing.embedder import HashingEmbedder
from p14_search.indexing.store import Store
from p14_search.procedure.model import SINK, SOURCE, build_net
from p14_search.procedure.soundness import check_soundness, enabled, fire
from p14_search.security.principals import PrincipalRegistry
from p14_search.services import build_services
from test_answer import fake_respond

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
QUESTION = "Quante giornate di lavoro agile al mese?"


def test_answer_net_is_a_sound_workflow_net():
    result = check_soundness(build_answer_net())
    assert result["workflow_net"]["ok"] and result["bounded"]
    assert result["option_to_complete"] and result["proper_completion"] and result["no_dead_transitions"]
    assert result["sound"]


def test_soundness_check_detects_a_missing_fallback_and_a_missing_idk():
    # without the extractive step a question whose LLM call failed would wait in p_extractive for ever
    no_fallback = build_net(tuple(s for s in STEPS if s.id != "t_extract"))
    result = check_soundness(no_fallback)
    assert not result["sound"] and {"p_extractive": 1} in result["markings_that_cannot_complete"]
    assert "t_extracted_some" in result["dead_transitions"]
    # without "I don't know" a question with insufficient evidence would never be answered
    result = check_soundness(build_net(tuple(s for s in STEPS if s.id != "t_idk")))
    assert not result["sound"] and {"p_no_answer": 1} in result["markings_that_cannot_complete"]


def test_every_run_ends_in_a_cited_answer_or_i_dont_know_and_the_pnml_matches():
    import build_answer_flow_model as exporter

    net = build_answer_net()
    runs = exporter.end_transitions(net)
    assert runs["every_run_ends_in_answer_or_i_dont_know"] and runs["runs_ending_in_answer_with_citations"] > 0
    assert set(runs["runs_by_end_transition"]) == {END_ANSWER, *END_IDK}
    pnml = ET.fromstring(exporter.pnml(net, "answer_flow", "answer"))
    assert len(pnml.findall(".//place")) == len(net.places) and len(pnml.findall(".//transition")) == len(net.transitions)
    assert len(pnml.findall(".//arc")) == len(net.arcs)
    assert set(exporter.POSITION) == set(net.places) | set(net.transitions)


# --- the net against the real service ------------------------------------------------------------
def make_client(tmp_path, respond=None, **settings) -> TestClient:
    """In-process API over the test corpus; respond = FakeProvider function, None = no LLM configured."""
    cfg = Settings(_env_file=None, display_system="S2", shadow_system=None, llm_provider="", llm_cache_dir=tmp_path / "cache",
                   llm_usage_log=tmp_path / "usage.jsonl", **settings)
    services = build_services(cfg, store=Store(":memory:"), qdrant=QdrantClient(":memory:"), embedder=HashingEmbedder(),
                              registry=PrincipalRegistry(PRINCIPALS), llm_provider=FakeProvider(respond) if respond else None)
    client = TestClient(create_app(cfg, services=services))
    for item in CORPUS:
        assert client.post("/v1/documents", json=ingest_payload(*item), headers={"X-API-Key": "key-admin"}).status_code == 202
        assert client.post(f"/v1/documents/test:{item[0]}/approve", headers={"X-API-Key": "key-admin"}).status_code == 200
    return client


def ask(client: TestClient, query: str, **extra) -> dict:
    r = client.post("/v1/answer", json={"query": query, **extra}, headers={"X-API-Key": "key-internal"})
    assert r.status_code == 200, r.text
    return r.json()


def trace(body: dict, llm_failed: str | None = None) -> list[str]:
    """Transitions that the service took for this response. llm_failed: None | 'answer' | 'support' (which call
    raised: the response alone cannot tell a fallback from a requested extractive answer)."""
    out = ["t_receive", "t_language", "t_retrieve", "t_translate_fuse" if body["query_italian"] else "t_no_translation", "t_sources"]
    report = body["verification"]
    if body["sentences"]:
        if body["mode"] == "llm_verified":
            out += ["t_llm_call", "t_llm_text", "t_verify", "t_kept"]
        elif body["mode"] == "llm":
            out += ["t_llm_call", "t_llm_text", "t_skip_verifier"]
        else:
            out += {None: ["t_mode_extractive"], "answer": ["t_llm_call", "t_llm_failed"],
                    "support": ["t_llm_call", "t_llm_text", "t_verifier_llm_failed"]}[llm_failed]
            out += ["t_extract", "t_extracted_some"]
        return out + ["t_respond"]
    if report is None:
        out += ["t_insufficient"]
    elif report["generated_sentences"] == 0:
        out += ["t_llm_call", "t_llm_no_answer"]
    else:
        out += ["t_llm_call", "t_llm_text", "t_verify", "t_all_dropped"]
    out += ["t_idk"]
    if body["handoff"] is None:
        return out + ["t_no_handoff"]
    return out + ["t_choose_office", "t_draft" if body["handoff"]["draft"] else "t_out_of_scope"]


def replay(transitions: list[str]) -> None:
    net = build_answer_net()
    marking = Counter({SOURCE: 1})
    for tid in transitions:
        assert tid in enabled(net, marking), f"{tid} is not enabled in {dict(+marking)}"
        marking = fire(net, marking, tid)
    assert +marking == Counter({SINK: 1})


def failing(when: str):
    def respond(system: str, prompt: str) -> str:
        if system.startswith(when):
            raise ConnectionError("local server stopped")
        return fake_respond(system, prompt)

    return respond


def test_real_responses_are_runs_of_the_net(tmp_path):
    seen: set[str] = set()

    def check(body: dict, end: str, llm_failed: str | None = None) -> dict:
        steps = trace(body, llm_failed)
        assert steps[-1] == end
        replay(steps)
        seen.update(steps)
        return body

    # no LLM configured: extractive answer
    assert check(ask(make_client(tmp_path / "a"), QUESTION), "t_respond")["mode"] == "extractive"
    llm = make_client(tmp_path / "b", fake_respond)
    assert check(ask(llm, QUESTION), "t_respond")["mode"] == "llm_verified"
    assert check(ask(llm, "How many smart working days per month can I do?"), "t_respond")["query_italian"]
    assert check(ask(llm, QUESTION, mode="llm"), "t_respond")["mode"] == "llm"
    # NO_ANSWER -> "I don't know": draft for the office, no draft requested, no office matches
    assert check(ask(llm, "nessunarisposta: quando esce la graduatoria della borsa di studio?"), "t_draft")["handoff"]["draft"]
    check(ask(llm, "nessunarisposta: quando esce la graduatoria della borsa di studio?", with_handoff=False), "t_no_handoff")
    assert check(ask(llm, "nessunarisposta sulla ricetta della carbonara"), "t_out_of_scope")["handoff"]["out_of_scope"]
    # the verifier drops everything: no sentence carries a citation
    uncited = make_client(tmp_path / "c", lambda s, p: "senza fonte" if s.startswith("Translate") else "Frase senza citazione.")
    assert check(ask(uncited, QUESTION), "t_draft" if ask(uncited, QUESTION)["handoff"]["draft"] else "t_out_of_scope")["verification"]
    # evidence below the threshold: the LLM is never asked
    weak = make_client(tmp_path / "d", fake_respond, ie_min_dense=2.0)
    body = check(ask(weak, QUESTION, with_handoff=False), "t_no_handoff")
    assert body["mode"] == "insufficient_evidence" and body["verification"] is None
    # LLM failure -> extractive fallback, in the answer call and in the support check
    assert check(ask(make_client(tmp_path / "e", failing("You are UniBridge")), QUESTION), "t_respond", "answer")["mode"] == "extractive"
    assert check(ask(make_client(tmp_path / "f", failing("You check citations")), QUESTION), "t_respond", "support")["mode"] == "extractive"
    # every transition of the model was taken by a real response, except the one case the test corpus cannot produce
    assert seen == set(build_answer_net().transitions) - {"t_extracted_none"}


def test_trace_outside_the_model_is_rejected():
    with pytest.raises(AssertionError):  # an answer returned without the verifier or the fallback is not a run of the net
        replay(["t_receive", "t_language", "t_retrieve", "t_no_translation", "t_sources", "t_llm_call", "t_respond"])
