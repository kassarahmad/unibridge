"""The answer pipeline of AnswerService.answer() (service.py) as a workflow net.

One token is one question. The net uses the same Net/Step classes as the scholarship procedure
(procedure/model.py) and is checked by the same soundness code (procedure/soundness.py); it is exported as PNML
and checked again with pm4py by scripts/build_answer_flow_model.py.

Soundness of this net means, for the service: whatever branch is taken (translation or not, evidence or not, LLM
answer, LLM failure, verifier dropping every sentence), the request always reaches exactly one of the four end
transitions, with nothing left half-done; and no branch of the model is unreachable.
End transitions: t_respond (answer, every sentence with its passages), t_draft ("I don't know" + e-mail draft),
t_out_of_scope ("I don't know", no office matches the question), t_no_handoff ("I don't know", draft not requested).

Each transition names the code it stands for; XOR choices are places with several output transitions.
tests/test_answer_flow.py replays real API responses on the net, so a change of the service that the net does
not allow makes a test fail.
"""

from __future__ import annotations

from p14_search.procedure.model import Net, Step, build_net

# lane = the component that acts; kind as in procedure/model.py (task | event | gateway_branch)
STEPS: tuple[Step, ...] = (
    Step("t_receive", "Receive the question (POST /v1/answer)", "api", "event", ("i",), ("p_question",)),
    Step("t_language", "Detect the language of the question", "answer", "task", ("p_question",), ("p_language",)),
    Step("t_retrieve", "Hybrid retrieval S2 (BM25 + dense, RRF) with the permission filter", "retrieval", "task",
         ("p_language",), ("p_first_ranking",)),
    # XOR: second retrieval with the Italian translation of the question
    Step("t_translate_fuse", "Translate the question into Italian, retrieve again, fuse the rankings (RRF)", "answer", "task",
         ("p_first_ranking",), ("p_ranking",)),
    Step("t_no_translation", "Keep the first ranking (Italian question, extractive mode or translation failed)", "answer",
         "gateway_branch", ("p_first_ranking",), ("p_ranking",)),
    Step("t_sources", "Load the passages, re-check permissions, number them P1..Pk", "retrieval", "task",
         ("p_ranking",), ("p_sources",)),
    # XOR: evidence and answer mode
    Step("t_insufficient", "No passage, or evidence below the calibrated threshold", "answer", "gateway_branch",
         ("p_sources",), ("p_no_answer",)),
    Step("t_mode_extractive", "Extractive mode (requested, or no LLM configured)", "answer", "gateway_branch",
         ("p_sources",), ("p_extractive",)),
    Step("t_llm_call", "Ask the LLM for an answer with one citation per sentence", "llm", "task", ("p_sources",), ("p_llm_called",)),
    # XOR: outcome of the LLM call
    Step("t_llm_failed", "LLM unavailable (error, timeout or spend limit): extractive fallback", "llm", "gateway_branch",
         ("p_llm_called",), ("p_extractive",)),
    Step("t_llm_no_answer", "The LLM replies NO_ANSWER (or nothing)", "llm", "gateway_branch", ("p_llm_called",), ("p_no_answer",)),
    Step("t_llm_text", "The LLM returns sentences with citations", "llm", "gateway_branch", ("p_llm_called",), ("p_generated",)),
    # XOR: verifier
    Step("t_verify", "Verifier: drop sentences without a valid citation or not supported by the cited passage", "verifier",
         "task", ("p_generated",), ("p_verified",)),
    Step("t_verifier_llm_failed", "LLM unavailable during the support check: extractive fallback", "verifier", "gateway_branch",
         ("p_generated",), ("p_extractive",)),
    Step("t_skip_verifier", "Mode 'llm' (evaluation only): citations parsed, not verified", "verifier", "gateway_branch",
         ("p_generated",), ("p_answer",)),
    Step("t_kept", "At least one sentence passes the verifier", "verifier", "gateway_branch", ("p_verified",), ("p_answer",)),
    Step("t_all_dropped", "The verifier drops every sentence", "verifier", "gateway_branch", ("p_verified",), ("p_no_answer",)),
    # extractive answer (chosen mode or fallback)
    Step("t_extract", "Copy sentences from the passages, each with its passage", "answer", "task", ("p_extractive",), ("p_extracted",)),
    Step("t_extracted_some", "At least one sentence extracted", "answer", "gateway_branch", ("p_extracted",), ("p_answer",)),
    Step("t_extracted_none", "No sentence could be extracted", "answer", "gateway_branch", ("p_extracted",), ("p_no_answer",)),
    # end: answer with citations
    Step("t_respond", "Return the answer: every sentence with its passages and their Italian originals", "api", "event",
         ("p_answer",), ("o",)),
    # end: "I don't know" and handoff
    Step("t_idk", "Say \"I don't know\" in the language of the question", "answer", "task", ("p_no_answer",), ("p_idk",)),
    Step("t_no_handoff", "Return \"I don't know\" (draft not requested: with_handoff = false)", "api", "event", ("p_idk",), ("o",)),
    Step("t_choose_office", "Choose the responsible office with the rule table", "handoff", "task", ("p_idk",), ("p_office",)),
    Step("t_draft", "Return \"I don't know\" with the e-mail draft for the office (never sent)", "handoff", "event",
         ("p_office",), ("o",)),
    Step("t_out_of_scope", "No office matches: return \"I don't know\" without a draft", "handoff", "event", ("p_office",), ("o",)),
)

END_ANSWER = "t_respond"
END_IDK = ("t_draft", "t_out_of_scope", "t_no_handoff")


def build_answer_net() -> Net:
    return build_net(STEPS)
